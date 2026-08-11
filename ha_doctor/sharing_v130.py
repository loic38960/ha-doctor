"""HA Doctor 0.13 compact support export with decisions and V8 evidence."""

import json
import sharing_v120 as base
from contracts_v130 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    DECISION_MODEL, CONDITION_MODEL,
)

MODEL = SHARE_MODEL
SCHEMA = SHARE_SCHEMA
TARGET_BYTES = SHARE_TARGET_BYTES
HARD_BYTES = SHARE_HARD_BYTES


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _decision_compact(report):
    decision = report.get("decision_engine") or {}
    items = []
    for raw in decision.get("top") or []:
        if not isinstance(raw, dict):
            continue
        playbook = raw.get("repair_playbook") or {}
        steps = playbook.get("steps") or []
        items.append({
            "id": raw.get("id"),
            "title": raw.get("title"),
            "priority": raw.get("priority"),
            "severity": raw.get("severity"),
            "operational_relevance": raw.get("operational_relevance"),
            "repair_readiness": playbook.get("repair_readiness"),
            "category": playbook.get("category"),
            "first_step": (steps[0] or {}).get("detail") if steps else None,
            "dependency_impact": raw.get("dependency_impact") or {},
        })
    return {
        "model": decision.get("model") or DECISION_MODEL,
        "total": decision.get("total", 0),
        "repair_readiness_counts": decision.get("repair_readiness_counts") or {},
        "operational_relevance_counts": decision.get("operational_relevance_counts") or {},
        "entity_attention": decision.get("entity_attention") or {},
        "top": items[:5],
        "automatic_fix": False,
        "read_only": True,
    }


def _guard_compact(report):
    sem = report.get("condition_semantics") or {}
    items = []
    for pair in sem.get("unproven_pairs") or []:
        if not isinstance(pair, dict) or not pair.get("v8_guard_matrix"):
            continue
        matrix = pair.get("v8_guard_matrix") or {}
        items.append({
            "entity_id": pair.get("entity_id"),
            "automations": list(pair.get("automations") or [])[:2],
            "target_kind": pair.get("target_kind"),
            "proof_count": matrix.get("proof_count", 0),
            "common_guard_entity_count": matrix.get("common_guard_entity_count", 0),
            "status": matrix.get("status"),
            "numeric_overlap_candidates": list((pair.get("v7_evidence") or {}).get("numeric_overlap_candidates") or [])[:3],
            "templates_executed": False,
        })
    return {
        "model": sem.get("model") or CONDITION_MODEL,
        "resolved_pair_count": sem.get("resolved_pair_count", 0),
        "mandatory_guard_resolved_pair_count": sem.get("mandatory_guard_resolved_pair_count", 0),
        "physical_unproven_pair_count": sem.get("physical_unproven_pair_count", 0),
        "helper_unproven_pair_count": sem.get("helper_unproven_pair_count", 0),
        "review_items": items[:4],
    }


def build_share_report(report):
    payload = base.build_share_report(report)
    if not isinstance(payload, dict):
        return payload
    payload["version"] = VERSION
    payload["report_schema"] = {**(payload.get("report_schema") or {}), "version": REPORT_SCHEMA}
    payload["share_schema"] = {"version": SCHEMA, "model": MODEL, "source_report_version": VERSION, "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES}
    payload["decision_engine"] = _decision_compact(report)
    payload["controller_guard_matrix"] = _guard_compact(report)

    public = payload.setdefault("public_contracts", {})
    public.update({
        "diagnostic_source": (report.get("diagnostic_summary") or {}).get("source"),
        "action_plan_model": (report.get("action_plan") or {}).get("model"),
        "controller_review_model": (report.get("controller_review_summary") or {}).get("model"),
        "condition_model": (report.get("condition_semantics") or {}).get("model"),
        "decision_model": (report.get("decision_engine") or {}).get("model"),
    })
    product = payload.setdefault("product_intelligence", {})
    source_product = report.get("product_intelligence") or {}
    product["model"] = source_product.get("model")
    product["decision_engine"] = source_product.get("decision_engine") or {}
    product["entity_attention"] = source_product.get("entity_attention") or {}
    product["public_contract_truth"] = source_product.get("public_contract_truth") or {}

    meta = payload.setdefault("export_meta", {})
    meta.update({
        "type": MODEL, "source_report_version": VERSION, "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES,
        "contract_source": "contracts_v130", "decision_engine_preserved": True,
        "controller_guard_matrix_preserved": True, "canonical_temporal_trace_preserved": True,
        "essential_controller_evidence_preserved": True, "essential_resilience_trace_preserved": True,
        "raw_states_included": False, "raw_yaml_included": False, "secret_values_included": False,
    })

    if _size(payload) > TARGET_BYTES:
        payload.pop("architecture_summary", None); payload.pop("entity_health_summary", None); payload.pop("non_plan_observations", None)
        (payload.get("product_intelligence") or {}).pop("score_change_explainer", None)
    if _size(payload) > TARGET_BYTES:
        payload.pop("registry_summary", None); payload.pop("entity_lineage_summary", None)
        decision = payload.get("decision_engine") or {}
        decision["top"] = list(decision.get("top") or [])[:3]
    if _size(payload) > TARGET_BYTES:
        for finding in payload.get("findings") or []:
            if isinstance(finding, dict):
                for key in list(finding):
                    if key not in {"rule_id", "title", "severity", "domain", "priority", "example_count"}:
                        finding.pop(key, None)
    if _size(payload) > HARD_BYTES:
        payload.pop("system", None); payload.pop("flow_confidence", None); payload.pop("root_cause_summary", None); payload.pop("temporal_analysis", None)
        (payload.get("decision_engine") or {}).pop("top", None)

    meta["share_report_bytes_estimate"] = _size(payload)
    meta["within_target_bytes"] = meta["share_report_bytes_estimate"] <= TARGET_BYTES
    meta["within_hard_bytes"] = meta["share_report_bytes_estimate"] <= HARD_BYTES
    meta["detail_level"] = "decision_evidence_first"
    return payload


def build_markdown_summary(report):
    text = base.build_markdown_summary(report).rstrip()
    decision = report.get("decision_engine") or {}
    sem = report.get("condition_semantics") or {}
    attention = decision.get("entity_attention") or {}
    return "\n".join([
        text, "", "## Decision Engine 0.13", "",
        f"- Prêtes pour modification manuelle : {decision.get('ready_for_manual_change_count',0)}",
        f"- Revues logiques : {decision.get('needs_logic_review_count',0)}",
        f"- Dépendances externes : {decision.get('external_dependency_count',0)}",
        f"- Paires résolues par garde obligatoire : {sem.get('mandatory_guard_resolved_pair_count',0)}",
        f"- Incidents registre sans impact automation : {attention.get('registry_actions_without_automation_impact',0)}",
        "- HA Doctor reste en lecture seule : les playbooks décrivent des modifications manuelles, ils ne les appliquent pas.", "",
    ])
