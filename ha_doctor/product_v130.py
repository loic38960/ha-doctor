"""HA Doctor 0.13 product layer: decisions, operational relevance and V8 evidence."""

import product_v120 as base
from contracts_v130 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    PRODUCT_MODEL, TRIAGE_MODEL, TRUST_MODEL, CONDITION_MODEL, CONTROLLER_REVIEW_MODEL,
    ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE, DECISION_MODEL, ENTITY_ATTENTION_MODEL,
    HISTORY_CONTRACT, TEMPORAL_MODEL,
)
from decision_v130 import build_decision_engine


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def _refresh_controller_v4(report):
    sem = report.get("condition_semantics") or {}
    summary = report.setdefault("controller_review_summary", {})
    remaining = [x for x in sem.get("unproven_pairs") or [] if isinstance(x, dict)]
    physical = [x for x in remaining if str(x.get("target_kind") or "") == "actuator"]
    helper = [x for x in remaining if str(x.get("target_kind") or "") == "helper"]
    matrix_items = [x for x in physical if x.get("v8_guard_matrix")]
    summary.update({
        "model": CONTROLLER_REVIEW_MODEL,
        "semantic_model": CONDITION_MODEL,
        "entity_count": len({str(x.get("entity_id")) for x in remaining if x.get("entity_id")}),
        "pair_count": len(remaining),
        "physical_pair_count": len(physical),
        "helper_pair_count": len(helper),
        "other_pair_count": max(0, len(remaining) - len(physical) - len(helper)),
        "mandatory_guard_resolved_pair_count": _int(sem.get("mandatory_guard_resolved_pair_count"), 0),
        "guard_matrix_review_pair_count": len(matrix_items),
        "remaining_physical_entities": sorted({str(x.get("entity_id")) for x in physical if x.get("entity_id")}),
    })
    for item in (report.get("action_plan") or {}).get("items") or []:
        if isinstance(item, dict) and item.get("id") == "DX-HD-AUTO-003":
            item["controller_review_summary"] = dict(summary)
    return summary


def _sync_doctor_actions(report, decision):
    doctor = report.setdefault("doctor_view", {})
    by_id = {str(x.get("id")): x for x in decision.get("items") or [] if isinstance(x, dict) and x.get("id")}
    enriched = []
    for raw in doctor.get("next_best_actions") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        d = by_id.get(str(item.get("id") or "")) or {}
        item["operational_relevance"] = d.get("operational_relevance")
        playbook = d.get("repair_playbook") or {}
        item["repair_readiness"] = playbook.get("repair_readiness")
        item["first_manual_step"] = ((playbook.get("steps") or [{}])[0] or {}).get("detail") if playbook.get("steps") else None
        enriched.append(item)
    doctor["next_best_actions"] = enriched
    doctor["decision_summary"] = {
        "model": DECISION_MODEL,
        "ready_for_manual_change": decision.get("ready_for_manual_change_count", 0),
        "needs_logic_review": decision.get("needs_logic_review_count", 0),
        "external_dependency": decision.get("external_dependency_count", 0),
        "high_operational_relevance": (decision.get("operational_relevance_counts") or {}).get("high", 0),
    }


def _refresh_quality(report, decision):
    quality = report.setdefault("quality_gates", {})
    gates = [x for x in quality.get("gates") or [] if isinstance(x, dict)]
    sem = report.get("condition_semantics") or {}
    for gate in gates:
        if gate.get("key") == "condition_semantics":
            gate["detail"] = (
                f"{sem.get('resolved_pair_count',0)} résolue(s) · "
                f"{sem.get('mandatory_guard_resolved_pair_count',0)} par garde obligatoire · "
                f"{sem.get('physical_unproven_pair_count',0)} physique(s) à revoir · "
                f"{sem.get('helper_unproven_pair_count',0)} helper(s)"
            )
    decision_gate = next((x for x in gates if x.get("key") == "decision_engine"), None)
    complete = decision.get("total", 0) == len(decision.get("items") or []) and all((x.get("repair_playbook") or {}).get("repair_readiness") for x in decision.get("items") or [])
    payload = {
        "key": "decision_engine", "label": "Plans de décision et réparation",
        "status": "pass" if complete else "warning",
        "detail": f"{decision.get('total',0)} diagnostic(s) · {decision.get('ready_for_manual_change_count',0)} prêt(s) pour modification manuelle · {decision.get('needs_logic_review_count',0)} revue(s) logique(s)",
    }
    if decision_gate:
        decision_gate.update(payload)
    else:
        gates.append(payload)
    quality["gates"] = gates
    counts = {}
    for gate in gates:
        status = str(gate.get("status") or "pass")
        counts[status] = counts.get(status, 0) + 1
    quality["counts"] = counts
    quality["overall"] = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")
    quality["non_pass_gates"] = [{k: x.get(k) for k in ("key", "label", "status", "detail")} for x in gates if x.get("status") != "pass"]


def _public_truth_v2(report, decision):
    return {
        "model": "public_contract_truth_v2_decision_engine",
        "version_fresh": report.get("version") == VERSION,
        "report_schema_fresh": (report.get("report_schema") or {}).get("version") == REPORT_SCHEMA,
        "share_schema_fresh": (report.get("share_contract") or {}).get("schema") == SHARE_SCHEMA,
        "diagnostic_source_fresh": (report.get("diagnostic_summary") or {}).get("source") == ACTION_PLAN_SOURCE,
        "action_plan_model_fresh": (report.get("action_plan") or {}).get("model") == ACTION_PLAN_MODEL,
        "controller_review_model_fresh": (report.get("controller_review_summary") or {}).get("model") == CONTROLLER_REVIEW_MODEL,
        "condition_model_fresh": (report.get("condition_semantics") or {}).get("model") == CONDITION_MODEL,
        "temporal_model_fresh": (report.get("temporal_analysis") or {}).get("model") == TEMPORAL_MODEL,
        "decision_model_fresh": decision.get("model") == DECISION_MODEL,
        "decision_item_identity": decision.get("total", 0) == len((report.get("action_plan") or {}).get("items") or []),
    }


def _rebuild_executive(report, decision):
    executive = report.setdefault("executive_summary", {})
    sem = report.get("condition_semantics") or {}
    attention = decision.get("entity_attention") or {}
    old = str(executive.get("text") or "")
    old = old.replace("Contrôleurs V7", "Contrôleurs V8")
    executive.update({
        "product_model": "product_intelligence_v5_decision_engine",
        "decision_engine_model": DECISION_MODEL,
        "entity_attention_model": ENTITY_ATTENTION_MODEL,
        "decision_ready_for_manual_change": decision.get("ready_for_manual_change_count", 0),
        "decision_needs_logic_review": decision.get("needs_logic_review_count", 0),
        "decision_external_dependency": decision.get("external_dependency_count", 0),
        "mandatory_guard_resolved_pair_count": _int(sem.get("mandatory_guard_resolved_pair_count"), 0),
        "registry_zero_impact_action_count": _int(attention.get("registry_actions_without_automation_impact"), 0),
        "text": old + (
            f" Decision Engine : {decision.get('ready_for_manual_change_count',0)} action(s) prête(s) pour modification manuelle, "
            f"{decision.get('needs_logic_review_count',0)} revue(s) logique(s), {decision.get('external_dependency_count',0)} dépendance(s) externe(s). "
            f"V8 : {sem.get('mandatory_guard_resolved_pair_count',0)} paire(s) résolue(s) par garde obligatoire."
        ),
    })


def apply_product_intelligence_v5(report):
    if not isinstance(report, dict):
        return report
    base.apply_product_intelligence_v4(report)
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report.setdefault("action_plan", {})["model"] = ACTION_PLAN_MODEL
    report.setdefault("diagnostic_summary", {})["source"] = ACTION_PLAN_SOURCE
    report["diagnostic_summary"]["plan_id_count"] = len((report.get("action_plan") or {}).get("items") or [])

    decision = build_decision_engine(report)
    _refresh_controller_v4(report)
    _sync_doctor_actions(report, decision)
    _refresh_quality(report, decision)
    report["share_contract"] = {"schema": SHARE_SCHEMA, "model": SHARE_MODEL, "target_bytes": SHARE_TARGET_BYTES, "hard_bytes": SHARE_HARD_BYTES, "single_source_of_truth": True}

    product = report.setdefault("product_intelligence", {})
    product["model"] = "product_intelligence_v5_decision_engine"
    product["decision_engine"] = {k: decision.get(k) for k in ("model", "total", "repair_readiness_counts", "operational_relevance_counts", "ready_for_manual_change_count", "needs_logic_review_count", "external_dependency_count", "policy")}
    product["entity_attention"] = decision.get("entity_attention") or {}
    truth = _public_truth_v2(report, decision)
    product["public_contract_truth"] = truth
    product.setdefault("cross_section_truth", {})["public_contracts_fresh"] = all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity"))

    doctor = report.setdefault("doctor_view", {})
    doctor["model"] = PRODUCT_MODEL
    trust = dict(doctor.get("trust") or report.get("diagnostic_trust") or {})
    trust.update({
        "model": TRUST_MODEL,
        "decision_engine_complete": decision.get("total", 0) == len(decision.get("items") or []),
        "mandatory_guard_proofs_only": True,
        "automatic_fix": False,
        "read_only": True,
    })
    doctor["trust"] = trust
    report["diagnostic_trust"] = trust
    report.setdefault("triage_board", {})["model"] = TRIAGE_MODEL

    _rebuild_executive(report, decision)
    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for cap in (
        "condition_semantics_v8_mandatory_guard_matrix", "mandatory_guard_exclusion_proof",
        "decision_engine_v1_evidence_playbooks", "repair_playbook_v1_read_only",
        "entity_attention_v2_operational_relevance", "operational_relevance_priority",
        "controller_review_summary_v4_guard_matrix", "public_contract_truth_v2_decision_engine",
        "decision_quality_gate", "read_only_repair_guidance",
    ):
        if cap not in capabilities:
            capabilities.append(cap)
    schema["capabilities"] = capabilities
    return report
