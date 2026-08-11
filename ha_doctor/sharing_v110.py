"""HA Doctor 0.11 support export with essential evidence preserved."""

import json

import sharing_v100 as base
from contracts_v110 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL,
    SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
)

MODEL = SHARE_MODEL
SCHEMA = SHARE_SCHEMA
TARGET_BYTES = SHARE_TARGET_BYTES
HARD_BYTES = SHARE_HARD_BYTES


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _controller_compact(report):
    product = report.get("product_intelligence") or {}
    trace = product.get("controller_review_trace") or {}
    return {
        "model": trace.get("model"),
        "physical_pair_count": trace.get("physical_pair_count", 0),
        "numeric_overlap_pair_count": trace.get("numeric_overlap_pair_count", 0),
        "items": [
            {
                "entity_id": x.get("entity_id"),
                "automations": list(x.get("automations") or [])[:2],
                "review_priority": x.get("review_priority"),
                "reason": x.get("reason"),
                "evidence_level": x.get("evidence_level"),
                "opposing_deterministic_intents": x.get("opposing_deterministic_intents"),
                "numeric_overlap_candidates": list(x.get("numeric_overlap_candidates") or [])[:3],
                "numeric_disjoint_evidence": list(x.get("numeric_disjoint_evidence") or [])[:2],
                "templates_executed": False,
            }
            for x in trace.get("items") or [] if isinstance(x, dict)
        ][:4],
    }


def _resilience_compact(report):
    analysis = report.get("resilience_analysis") or {}
    recs = report.get("resilience_recommendations") or {}
    return {
        "analysis": {
            key: analysis.get(key)
            for key in (
                "model", "critical_dependency_count", "external_spof_count", "review_count",
                "partial_count", "protected_count", "unprotected_automation_count",
                "weak_physical_automation_count", "physical_control_consumer_count",
            ) if key in analysis
        },
        "recommendations": {
            "model": recs.get("model"),
            "count": recs.get("count", 0),
            "must_fix_count": recs.get("must_fix_count", 0),
            "hardening_count": recs.get("hardening_count", 0),
            "selection_policy": recs.get("selection_policy"),
            "items": [
                {
                    "entity_id": x.get("entity_id"),
                    "tier": x.get("tier"),
                    "criticality": x.get("criticality"),
                    "unprotected_physical_automation_count": x.get("unprotected_physical_automation_count", 0),
                    "weak_physical_automation_count": x.get("weak_physical_automation_count", 0),
                    "risky_automations": list(x.get("risky_automations") or [])[:5],
                }
                for x in recs.get("items") or [] if isinstance(x, dict)
            ][:3],
        },
    }


def _product_compact(report):
    p = report.get("product_intelligence") or {}
    keys = (
        "model", "score_projection", "entity_noise", "maintenance", "security",
        "diagnostic_coverage", "score_change_explainer", "score_change_trace",
        "evidence_summary", "cross_section_truth",
    )
    return {key: p.get(key) for key in keys if key in p}


def build_share_report(report):
    payload = base.build_share_report(report)
    if not isinstance(payload, dict):
        return payload
    payload["version"] = VERSION
    payload["report_schema"] = {**(payload.get("report_schema") or {}), "version": REPORT_SCHEMA}
    payload["share_schema"] = {
        "version": SCHEMA,
        "model": MODEL,
        "source_report_version": VERSION,
        "target_bytes": TARGET_BYTES,
        "hard_bytes": HARD_BYTES,
    }
    payload["product_intelligence"] = _product_compact(report)
    payload["controller_evidence"] = _controller_compact(report)
    payload["resilience"] = _resilience_compact(report)

    doctor = payload.get("doctor_view") or {}
    doctor["model"] = (report.get("doctor_view") or {}).get("model")
    doctor["trust"] = (report.get("doctor_view") or {}).get("trust") or {}
    payload["doctor_view"] = doctor

    meta = payload.setdefault("export_meta", {})
    meta.update({
        "type": MODEL,
        "source_report_version": VERSION,
        "target_bytes": TARGET_BYTES,
        "hard_bytes": HARD_BYTES,
        "contract_source": "contracts_v110",
        "essential_controller_evidence_preserved": True,
        "essential_resilience_trace_preserved": True,
        "raw_states_included": False,
        "raw_yaml_included": False,
        "secret_values_included": False,
    })

    if _size(payload) > TARGET_BYTES:
        payload.pop("architecture_summary", None)
        payload.pop("entity_health_summary", None)
        payload.pop("non_plan_observations", None)
        product = payload.get("product_intelligence") or {}
        product.pop("score_change_explainer", None)
    if _size(payload) > TARGET_BYTES:
        payload.pop("registry_summary", None)
        payload.pop("entity_lineage_summary", None)
        for finding in payload.get("findings") or []:
            if isinstance(finding, dict):
                for key in list(finding):
                    if key not in {"rule_id", "title", "severity", "domain", "priority", "example_count"}:
                        finding.pop(key, None)
    if _size(payload) > HARD_BYTES:
        payload.pop("system", None)
        payload.pop("flow_confidence", None)
        payload.pop("root_cause_summary", None)
        payload.pop("temporal_analysis", None)

    meta["share_report_bytes_estimate"] = _size(payload)
    meta["within_target_bytes"] = meta["share_report_bytes_estimate"] <= TARGET_BYTES
    meta["within_hard_bytes"] = meta["share_report_bytes_estimate"] <= HARD_BYTES
    meta["detail_level"] = "cross_validated_evidence_first"
    return payload


def build_markdown_summary(report):
    base_text = base.build_markdown_summary(report)
    product = report.get("product_intelligence") or {}
    security = product.get("security") or {}
    maintenance = product.get("maintenance") or {}
    controller = product.get("controller_review_trace") or {}
    resilience = product.get("resilience_trace") or {}
    lines = [
        base_text.rstrip(),
        "",
        "## Validation croisée 0.11",
        "",
        f"- Sécurité active : {security.get('active_secret_hint_count',0)} indice(s) · archives : {security.get('archive_secret_hint_count',0)}",
        f"- Références absentes : {maintenance.get('missing_reference_count',0)} · indisponibles locales à revoir : {maintenance.get('local_unavailable_review',0)}",
        f"- Contrôleurs physiques à revoir : {controller.get('physical_pair_count',0)} · overlaps numériques : {controller.get('numeric_overlap_pair_count',0)}",
        f"- Résilience : {resilience.get('must_fix_count',0)} exposition(s) réelle(s) · {resilience.get('hardening_count',0)} durcissement(s)",
        "",
    ]
    return "\n".join(lines)
