"""HA Doctor 0.10 compact exports with one central size contract."""

import json

import sharing_v090 as base
from contracts_v100 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL,
    SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
)

MODEL = SHARE_MODEL
SCHEMA = SHARE_SCHEMA
TARGET_BYTES = SHARE_TARGET_BYTES
HARD_BYTES = SHARE_HARD_BYTES


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _compact_product(report):
    product = report.get("product_intelligence") or {}
    return {
        "model": product.get("model"),
        "score_projection": product.get("score_projection") or {},
        "entity_noise": product.get("entity_noise") or {},
        "maintenance": product.get("maintenance") or {},
        "security": product.get("security") or {},
        "automation_reliability": product.get("automation_reliability") or {},
        "doctor_modes": product.get("doctor_modes") or {},
        "diagnostic_coverage": product.get("diagnostic_coverage") or {},
        "score_change_explainer": product.get("score_change_explainer") or {},
        "evidence_summary": product.get("evidence_summary") or {},
    }


def _compact_doctor(report):
    doctor = report.get("doctor_view") or {}
    actions = []
    for item in doctor.get("next_best_actions") or []:
        if not isinstance(item, dict):
            continue
        actions.append({key: item.get(key) for key in (
            "id", "title", "lane", "risk_score", "confidence_tier", "evidence_level",
            "repair_mode", "repair_safety", "effort", "estimated_score_gain",
            "dependency_impact", "impacted_automation_count",
        ) if key in item})
    return {
        "model": doctor.get("model"),
        "verdict": doctor.get("verdict") or {},
        "technical_health_score": doctor.get("technical_health_score"),
        "score_v5_preview": doctor.get("score_v5_preview"),
        "projected_after_top_3": doctor.get("projected_after_top_3"),
        "triage_counts": doctor.get("triage_counts") or {},
        "next_best_actions": actions[:10],
        "trust": doctor.get("trust") or {},
        "coverage": doctor.get("coverage") or {},
        "automatic_fix": False,
        "read_only": True,
    }


def _trim(payload, level):
    if level >= 1:
        payload.pop("architecture_summary", None)
        payload.pop("entity_health_summary", None)
        payload.pop("non_plan_observations", None)
    if level >= 2:
        product = payload.get("product_intelligence") or {}
        product.pop("automation_reliability", None)
        product.pop("doctor_modes", None)
        payload.pop("score_v5_preview", None)
    if level >= 3:
        payload.pop("registry_summary", None)
        payload.pop("entity_lineage_summary", None)
        payload.pop("root_cause_summary", None)
        product = payload.get("product_intelligence") or {}
        product.pop("maintenance", None)
        product.pop("security", None)
        for finding in payload.get("findings") or []:
            if isinstance(finding, dict):
                for key in list(finding):
                    if key not in {"rule_id", "title", "severity", "domain", "priority", "example_count"}:
                        finding.pop(key, None)
        for item in (payload.get("action_plan") or {}).get("items") or []:
            if isinstance(item, dict):
                for key in list(item):
                    if key not in {"id", "title", "priority", "severity", "domain", "confidence", "confidence_score", "source_type", "source_id"}:
                        item.pop(key, None)


def build_share_report(report):
    if not isinstance(report, dict):
        return None
    payload = base.build_share_report(report)
    if not isinstance(payload, dict):
        return payload

    payload["version"] = VERSION
    payload["doctor_view"] = _compact_doctor(report)
    payload["product_intelligence"] = _compact_product(report)
    payload["scan_performance"] = report.get("scan_performance") or {}
    payload["share_schema"] = {
        "version": SCHEMA,
        "model": MODEL,
        "source_report_version": VERSION,
        "target_bytes": TARGET_BYTES,
        "hard_bytes": HARD_BYTES,
    }
    payload.setdefault("report_schema", {})["version"] = REPORT_SCHEMA

    meta = payload.setdefault("export_meta", {})
    meta.update({
        "type": MODEL,
        "source_report_version": VERSION,
        "target_bytes": TARGET_BYTES,
        "hard_bytes": HARD_BYTES,
        "contract_source": "contracts_v100",
        "intended_for": "assistant_or_support_analysis",
        "raw_states_included": False,
        "raw_yaml_included": False,
        "secret_values_included": False,
        "full_dependency_graph_included": False,
        "all_action_identities_preserved": True,
        "all_finding_identities_preserved": True,
    })

    level = 0
    while _size(payload) > TARGET_BYTES and level < 3:
        level += 1
        _trim(payload, level)
    meta["detail_level"] = ["standard", "compact", "minimal", "identity_first"][level]

    if _size(payload) > HARD_BYTES:
        for key in (
            "system", "registry_summary", "flow_confidence", "condition_semantics",
            "entity_lineage_summary", "resilience", "root_cause_summary", "temporal_analysis",
            "score_v5_preview", "scan_performance",
        ):
            payload.pop(key, None)
        _trim(payload, 3)
        meta["detail_level"] = "hard_bounded_identity_first"
        meta["secondary_sections_omitted"] = True

    meta["share_report_bytes_estimate"] = _size(payload)
    meta["within_target_bytes"] = meta["share_report_bytes_estimate"] <= TARGET_BYTES
    meta["within_hard_bytes"] = meta["share_report_bytes_estimate"] <= HARD_BYTES
    return payload


def build_markdown_summary(report):
    doctor = report.get("doctor_view") or {}
    product = report.get("product_intelligence") or {}
    verdict = doctor.get("verdict") or {}
    projection = product.get("score_projection") or {}
    evidence = product.get("evidence_summary") or {}
    noise = product.get("entity_noise") or {}
    security = product.get("security") or {}
    maintenance = product.get("maintenance") or {}
    reliability = product.get("automation_reliability") or {}
    self_check = report.get("self_check") or {}

    lines = [
        "# Rapport HA Doctor",
        "",
        f"**Version :** {VERSION}",
        f"**Date :** {report.get('generated_at') or '—'}",
        f"**Verdict :** {verdict.get('label') or '—'}",
        f"**Score technique :** {(report.get('scores') or {}).get('global','—')}/100",
        f"**Confiance diagnostic :** {(doctor.get('trust') or {}).get('score','—')}/100",
        "",
        "## Projection",
        "",
    ]
    for key, label in (("after_top_1", "1 correction"), ("after_top_3", "3 corrections"), ("after_top_5", "5 corrections"), ("after_top_10", "10 corrections")):
        item = projection.get(key) or {}
        lines.append(f"- Après {label} : {item.get('score','—')}/100 (gain estimé +{item.get('estimated_gain',0)})")

    lines.extend([
        "",
        "## Preuves",
        "",
        f"- Confirmés : {evidence.get('confirmed',0)}",
        f"- Probables : {evidence.get('probable',0)}",
        f"- Hypothèses : {evidence.get('hypothesis',0)}",
        "",
        "## Bruit entités",
        "",
        f"- Unavailable bruts : {noise.get('raw_unavailable',0)} ; à examiner : {noise.get('unavailable_attention',0)}",
        f"- Unknown bruts : {noise.get('raw_unknown',0)} ; stateless ignorés : {noise.get('unknown_stateless_ignored',0)}",
        f"- Causes registry actionnables : {noise.get('registry_actionable_root_causes',0)}",
        "",
        "## Sécurité / maintenance / automations",
        "",
        f"- Sécurité : {security.get('posture','—')} · secrets actifs potentiels {security.get('active_secret_hint_count',0)}",
        f"- Orphelins probables : {maintenance.get('probable_orphans',0)} · références absentes {maintenance.get('missing_reference_count',0)}",
        f"- Conflits physiques à revoir : {reliability.get('physical_controller_pairs_to_review',0)}",
        "",
        "## Prochaines actions",
        "",
    ])
    for idx, item in enumerate(doctor.get("next_best_actions") or [], start=1):
        lines.append(
            f"{idx}. **{item.get('title') or item.get('id')}** — risque {item.get('risk_score','—')}/100 · "
            f"preuve {item.get('evidence_level','—')} · gain +{item.get('estimated_score_gain',0)}"
        )
    lines.extend([
        "",
        "## Auto-contrôle",
        "",
        f"- {self_check.get('status','—')} · {self_check.get('pass_count',0)}/{self_check.get('check_count',0)} contrôles réussis",
        "",
        "HA Doctor reste en lecture seule : aucune valeur de secret, aucun état brut et aucun YAML brut n'est inclus dans cet export.",
        "",
    ])
    return "\n".join(lines)
