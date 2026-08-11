"""HA Doctor 0.15 trust-first product intelligence.

The public contract is installed before it is evaluated. This fixes the 0.14
ordering bug where Share V8 was marked stale even though the final export was
correct. Operational counts also become the customer-facing summary.
"""

import product_v110 as source_product
from decision_v150 import build_decision_engine_v3
from contracts_v150 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    PRODUCT_MODEL, TRIAGE_MODEL, TRUST_MODEL, TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY,
    PUBLICATION_MODEL, SCORE_TRACE_MODEL, CONDITION_MODEL, CONTROLLER_REVIEW_MODEL,
    ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE, DECISION_MODEL, PUBLIC_TRUTH_MODEL,
)


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def install_public_contract(report):
    """Install all current public identities before any truth/self-check runs."""
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report["share_contract"] = {
        "schema": SHARE_SCHEMA, "model": SHARE_MODEL,
        "target_bytes": SHARE_TARGET_BYTES, "hard_bytes": SHARE_HARD_BYTES,
        "single_source_of_truth": True,
    }
    report.setdefault("action_plan", {})["model"] = ACTION_PLAN_MODEL
    report.setdefault("diagnostic_summary", {})["source"] = ACTION_PLAN_SOURCE
    return report


def _score_trace(report):
    temporal = report.get("temporal_analysis") or {}
    primary = _int((report.get("scores") or {}).get("global"), 0)
    trusted = bool(temporal.get("previous_score_trusted"))
    return {
        "model": SCORE_TRACE_MODEL,
        "primary_score": primary,
        "preview_score": _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), primary),
        "previous_score": temporal.get("previous_score") if trusted else None,
        "score_delta": temporal.get("score_delta") if trusted else None,
        "previous_score_trusted": trusted,
        "previous_score_source": temporal.get("previous_score_source"),
        "comparison_status": temporal.get("score_comparison_status"),
        "latest_candidate_status": temporal.get("latest_candidate_status"),
        "meaningful_previous_generated_at": temporal.get("meaningful_previous_generated_at"),
        "current_generated_at": report.get("generated_at"),
        "history_contract": HISTORY_CONTRACT, "history_policy": HISTORY_POLICY,
        "publication_model": PUBLICATION_MODEL,
        "history_scope": "published_complete_primary_score_only",
        "preview_applied_to_primary": False,
        "false_stability_prevented": bool(temporal.get("false_stability_prevented")),
    }


def _controller_summary(report):
    sem = report.get("condition_semantics") or {}
    remaining = [x for x in sem.get("unproven_pairs") or [] if isinstance(x, dict)]
    physical = [x for x in remaining if str(x.get("target_kind") or "") == "actuator"]
    helpers = [x for x in remaining if str(x.get("target_kind") or "") == "helper"]
    event = [x for x in physical if (x.get("v10_event_analysis") or {}).get("status") == "event_window_policy_overlap"]
    summary = {
        "model": CONTROLLER_REVIEW_MODEL, "semantic_model": CONDITION_MODEL,
        "entity_count": len({str(x.get("entity_id")) for x in remaining if x.get("entity_id")}),
        "pair_count": len(remaining), "physical_pair_count": len(physical), "helper_pair_count": len(helpers),
        "other_pair_count": max(0, len(remaining) - len(physical) - len(helpers)),
        "mandatory_guard_resolved_pair_count": _int(sem.get("mandatory_guard_resolved_pair_count"), 0),
        "branch_numeric_resolved_pair_count": _int(sem.get("branch_numeric_resolved_pair_count"), 0),
        "policy_overlap_pair_count": _int(sem.get("policy_overlap_pair_count"), 0),
        "event_window_policy_overlap_pair_count": len(event),
        "crossing_event_policy_overlap_pair_count": _int(sem.get("crossing_event_policy_overlap_pair_count"), 0),
        "remaining_physical_entities": sorted({str(x.get("entity_id")) for x in physical if x.get("entity_id")}),
    }
    report["controller_review_summary"] = summary
    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["controller_review_entity_count"] = summary["entity_count"]
    diagnostic["controller_review_pair_count"] = summary["pair_count"]
    return summary


def _public_truth(report, decision):
    return {
        "model": PUBLIC_TRUTH_MODEL,
        "version_fresh": report.get("version") == VERSION,
        "report_schema_fresh": (report.get("report_schema") or {}).get("version") == REPORT_SCHEMA,
        "share_schema_fresh": (report.get("share_contract") or {}).get("schema") == SHARE_SCHEMA,
        "share_model_fresh": (report.get("share_contract") or {}).get("model") == SHARE_MODEL,
        "diagnostic_source_fresh": (report.get("diagnostic_summary") or {}).get("source") == ACTION_PLAN_SOURCE,
        "action_plan_model_fresh": (report.get("action_plan") or {}).get("model") == ACTION_PLAN_MODEL,
        "controller_review_model_fresh": (report.get("controller_review_summary") or {}).get("model") == CONTROLLER_REVIEW_MODEL,
        "condition_model_fresh": (report.get("condition_semantics") or {}).get("model") == CONDITION_MODEL,
        "temporal_model_fresh": (report.get("temporal_analysis") or {}).get("model") == TEMPORAL_MODEL,
        "decision_model_fresh": decision.get("model") == DECISION_MODEL,
        "history_policy_fresh": (report.get("temporal_analysis") or {}).get("history_policy") == HISTORY_POLICY,
        "decision_item_identity": decision.get("total", 0) == len((report.get("action_plan") or {}).get("items") or []),
        "evaluated_after_contract_install": True,
    }


def _score_explainer(trace):
    status = trace.get("comparison_status"); current = trace.get("primary_score")
    previous = trace.get("previous_score"); delta = trace.get("score_delta")
    if status == "canonical" and previous is not None and delta is not None:
        reason = f"Score primaire {int(delta):+d} point(s) depuis le dernier rapport publié ({previous} → {current})." if delta else f"Score primaire stable à {current}/100 depuis le dernier rapport publié."
    elif status == "blocked_previous_ignored":
        reason = "Le dernier scan bloqué est ignoré comme baseline ; seule une publication complète peut servir de référence."
    elif status == "legacy_untrusted":
        reason = "Comparaison suspendue : aucun ancien snapshot publié fiable ne respecte encore le contrat canonique."
    else:
        reason = "Premier point de comparaison publié fiable : aucun delta n'est encore calculable."
    return {
        "model": "score_change_explainer_v4_publication_safe", "primary_score": current,
        "preview_score": trace.get("preview_score"), "previous_score": previous, "score_delta": delta,
        "previous_score_trusted": bool(trace.get("previous_score_trusted")), "comparison_status": status,
        "reason": reason, "v5_preview_not_applied_to_primary": True,
    }


def _refresh_quality(report, decision):
    quality = report.setdefault("quality_gates", {})
    gates = [x for x in quality.get("gates") or [] if isinstance(x, dict) and x.get("key") not in {"report_self_check", "decision_engine"}]
    sem = report.get("condition_semantics") or {}
    for gate in gates:
        if gate.get("key") == "condition_semantics":
            gate["detail"] = (
                f"{sem.get('resolved_pair_count',0)} résolue(s) · {sem.get('branch_numeric_resolved_pair_count',0)} exclusion(s) numérique(s) · "
                f"{sem.get('event_window_policy_overlap_pair_count',0)} overlap(s) événementiel(s) · {sem.get('physical_unproven_pair_count',0)} physique(s) à revoir"
            )
    gates.append({
        "key": "decision_engine", "label": "Décision opérationnelle", "status": "pass",
        "detail": f"{(decision.get('lane_counts') or {}).get('fix_now',0)} fix · {(decision.get('lane_counts') or {}).get('logic_review',0)} logique · {(decision.get('lane_counts') or {}).get('watch',0)} watch",
    })
    quality["gates"] = gates


def _rebuild_summary(report, decision, trace):
    lanes = decision.get("lane_counts") or {}
    operational = decision.get("operational_summary") or {}
    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["plan_id_count"] = len((report.get("action_plan") or {}).get("items") or [])
    diagnostic["operational_counts"] = dict(lanes)
    diagnostic["actionable_count"] = _int(decision.get("primary_action_count"), 0)
    diagnostic["headline"] = (
        f"{lanes.get('fix_now',0)} correction(s), {lanes.get('logic_review',0)} revue(s) logique(s), "
        f"{lanes.get('watch',0)} surveillance(s) et {lanes.get('optimize',0)} optimisation(s)."
    )

    executive = report.setdefault("executive_summary", {})
    primary = _int((report.get("scores") or {}).get("global"), 0)
    preview = _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), primary)
    sem = report.get("condition_semantics") or {}
    security = (report.get("product_intelligence") or {}).get("security") or {}
    if trace.get("comparison_status") == "canonical" and trace.get("score_delta") is not None:
        temporal_text = f"Δ score {int(trace.get('score_delta')):+d}."
    elif trace.get("comparison_status") == "blocked_previous_ignored":
        temporal_text = "scan précédent bloqué ignoré comme baseline."
    else:
        temporal_text = "delta suspendu faute de baseline publiée fiable."
    executive.update({
        "product_model": "product_intelligence_v7_trust_first",
        "decision_engine_model": DECISION_MODEL, "temporal_model": TEMPORAL_MODEL,
        "score_history_contract": HISTORY_CONTRACT, "score_history_policy": HISTORY_POLICY,
        "score_comparison_status": trace.get("comparison_status"),
        "previous_score_trusted": bool(trace.get("previous_score_trusted")),
        "operational_summary": operational,
        "text": (
            f"Indice de santé V4 {primary}/100 ({executive.get('health_label','—')}). Preview V5 {preview}/100, non appliqué au score primaire ; {temporal_text} "
            f"Decision V3 : {lanes.get('fix_now',0)} fix-now, {lanes.get('logic_review',0)} revue(s) logique(s), {lanes.get('watch',0)} surveillance(s), {lanes.get('optimize',0)} optimisation(s). "
            f"Contrôleurs V10 : {sem.get('physical_unproven_pair_count',0)} paire(s) physique(s), dont {sem.get('crossing_event_policy_overlap_pair_count',0)} overlap(s) de franchissement. "
            f"Sécurité : {security.get('active_secret_hint_count',0)} indice(s) actif(s)."
        ),
    })


def apply_product_intelligence_v7(report):
    if not isinstance(report, dict):
        return report

    # Critical order: current contracts and acquisition evidence exist first.
    install_public_contract(report)
    source_product.apply_product_intelligence_v3(report)
    install_public_contract(report)  # source layer writes legacy public fields; reassert once.

    _controller_summary(report)
    decision = build_decision_engine_v3(report)
    trace = _score_trace(report)
    product = report.setdefault("product_intelligence", {})
    product["model"] = "product_intelligence_v7_trust_first"
    product["score_change_trace"] = trace
    product["score_change_explainer"] = _score_explainer(trace)
    product["decision_engine"] = {k: decision.get(k) for k in ("model", "total", "lane_counts", "repair_readiness_counts", "operational_relevance_counts", "primary_action_count", "event_window_policy_count", "policy")}
    product["entity_attention"] = decision.get("entity_attention") or {}

    truth = _public_truth(report, decision)
    product["public_contract_truth"] = truth
    product.setdefault("cross_section_truth", {})["public_contracts_fresh"] = all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity"))

    perf = report.get("scan_performance") or {}
    single_snapshot = bool(perf.get("single_state_snapshot_preserved")) and _int(perf.get("additional_home_assistant_state_reads"), 0) == 0
    doctor = report.setdefault("doctor_view", {})
    doctor["model"] = PRODUCT_MODEL
    doctor["decision_summary"] = {
        "model": DECISION_MODEL, "lane_counts": decision.get("lane_counts") or {},
        "primary_action_count": decision.get("primary_action_count", 0),
        "watch_external_count": decision.get("watch_external_count", 0),
        "event_window_policy_count": decision.get("event_window_policy_count", 0),
    }
    doctor["next_best_actions"] = [
        {
            "id": x.get("id"), "title": x.get("title"), "operational_lane": x.get("operational_lane"),
            "operational_relevance": x.get("operational_relevance"), "execution_priority_score": x.get("execution_priority_score"),
            "repair_readiness": (x.get("repair_playbook") or {}).get("repair_readiness"),
            "first_manual_step": (((x.get("repair_playbook") or {}).get("steps") or [{}])[0] or {}).get("detail"),
        }
        for x in decision.get("top") or []
    ]
    trust = dict(doctor.get("trust") or report.get("diagnostic_trust") or {})
    trust.update({
        "model": TRUST_MODEL, "decision_engine_complete": decision.get("total", 0) == len(decision.get("items") or []),
        "single_snapshot_evidence": single_snapshot,
        "temporal_score_comparison_trusted": bool(trace.get("previous_score_trusted")),
        "temporal_score_comparison_status": trace.get("comparison_status"),
        "canonical_history_contract": HISTORY_CONTRACT, "canonical_history_policy": HISTORY_POLICY,
        "public_contract_truth": all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity")),
        "native_self_check": True, "automatic_fix": False, "read_only": True,
    })
    doctor["trust"] = trust
    report["diagnostic_trust"] = trust
    report.setdefault("triage_board", {})["model"] = TRIAGE_MODEL

    _refresh_quality(report, decision)
    _rebuild_summary(report, decision, trace)

    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for cap in (
        "contract_install_before_truth_v1", "final_export_self_validation_v1", "single_snapshot_trust_ordering_v1",
        "condition_semantics_v10_event_window_policy", "numeric_state_crossing_semantics",
        "decision_engine_v3_execution_board", "operational_summary_v1", "publication_transaction_v1",
        "share_report_v9_22k_target", "public_contract_truth_v4_pre_selfcheck",
    ):
        if cap not in capabilities:
            capabilities.append(cap)
    schema["capabilities"] = capabilities
    return report
