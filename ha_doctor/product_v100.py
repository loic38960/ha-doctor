"""HA Doctor 0.10 product intelligence: explainability, modes and noise control."""

from collections import Counter, defaultdict

import product_v090 as base
from contracts_v100 import (
    VERSION, REPORT_SCHEMA, PRODUCT_MODEL, TRIAGE_MODEL, TRUST_MODEL,
    SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
)

_PRIORITY_WEIGHT = {"action_now": 40, "verify": 24, "optimize": 10, "info": 2}
_SEVERITY_WEIGHT = {"critical": 32, "high": 25, "medium": 16, "low": 7, "info": 1}
_IMPACT_WEIGHT = {"critical": 16, "high": 12, "medium": 7, "low": 3, "none": 0}


def _num(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _int(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return int(default)


def evidence_level(item):
    score = _num(item.get("confidence_score"), 0.5)
    source = str(item.get("source_type") or "")
    if score >= 0.90 and source in {"finding", "registry_integration", "registry_device"}:
        return "confirmed"
    if score >= 0.68:
        return "probable"
    return "hypothesis"


def _risk_breakdown(item):
    priority = str(item.get("priority") or "info")
    severity = str(item.get("severity") or "info")
    impact = str((item.get("dependency_impact") or {}).get("level") or "none")
    temporal = str((item.get("temporal") or {}).get("status") or "")
    confidence = _num(item.get("confidence_score"), 0.5)
    components = {
        "priority": _PRIORITY_WEIGHT.get(priority, 0),
        "severity": _SEVERITY_WEIGHT.get(severity, 0),
        "dependency_impact": _IMPACT_WEIGHT.get(impact, 0),
        "persistence": 6 if temporal == "persistent" else (3 if temporal == "recurrent" else 0),
        "confidence": round(confidence * 6),
    }
    return {"components": components, "raw_total": sum(components.values()), "capped_at": 100}


def _gain_map(report):
    gains = {}
    for item in (report.get("score_v5_preview") or {}).get("why_lost_points") or []:
        if isinstance(item, dict) and item.get("id"):
            gains[str(item["id"])] = round(_num(item.get("v5_penalty", item.get("technical_penalty", 0))), 2)
    for item in (report.get("score_v5_preview") or {}).get("fix_scenarios") or []:
        if isinstance(item, dict) and item.get("id"):
            gains[str(item["id"])] = round(_num(item.get("estimated_gain", gains.get(str(item["id"]), 0))), 2)
    return gains


def _score_projection(report, normalized):
    preview = _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), _int((report.get("scores") or {}).get("global"), 0))
    fixable = [x for x in normalized if _num(x.get("estimated_score_gain"), 0) > 0]
    fixable.sort(key=lambda x: (-_num(x.get("estimated_score_gain")), -_int(x.get("risk_score"))))

    def projected(count):
        gain = round(sum(_num(x.get("estimated_score_gain"), 0) for x in fixable[:count]), 2)
        return {"fix_count": min(count, len(fixable)), "estimated_gain": gain, "score": min(100, round(preview + gain))}

    return {
        "model": "score_projection_v2_multi_horizon",
        "starting_preview_score": preview,
        "after_top_1": projected(1),
        "after_top_3": projected(3),
        "after_top_5": projected(5),
        "after_top_10": projected(10),
        "fixable_diagnostic_count": len(fixable),
        "assumption": "Chaque gain est indicatif et suppose la disparition complète du diagnostic sans effet secondaire.",
    }


def _health_noise(report):
    inv = report.get("inventory") or report.get("inventory_summary") or {}
    health = report.get("entity_health") or report.get("entity_health_summary") or {}
    unavailable = health.get("unavailable") or {}
    unknown = health.get("unknown") or {}
    registry = report.get("registry_analysis") or report.get("registry_summary") or {}

    raw_unavailable = _int(inv.get("unavailable_count", unavailable.get("total", 0)))
    raw_unknown = _int(inv.get("unknown_count", unknown.get("total", 0)))
    transient = _int(unavailable.get("likely_transient_count"), 0)
    optional = _int(unavailable.get("likely_optional_count"), 0)
    attention = _int(unavailable.get("attention_count", unavailable.get("review_count", raw_unavailable)))
    stateless = _int(unknown.get("ignored_stateless_count"), 0)
    unknown_attention = _int(unknown.get("attention_count", unknown.get("review_count", max(0, raw_unknown - stateless))))

    integration = registry.get("integration_health") or {}
    devices = registry.get("device_health") or {}
    actionable_registry = _int((report.get("root_cause_summary") or {}).get("actionable_registry_incidents"), 0)
    return {
        "model": "entity_noise_model_v1",
        "raw_unavailable": raw_unavailable,
        "raw_unknown": raw_unknown,
        "unavailable_transient_or_sleep_tolerant": transient,
        "unavailable_optional_or_secondary": optional,
        "unavailable_attention": attention,
        "unknown_stateless_ignored": stateless,
        "unknown_attention": unknown_attention,
        "registry_actionable_root_causes": actionable_registry,
        "integration_groups_affected": _int(integration.get("affected"), 0),
        "device_groups_offline": _int(devices.get("offline"), 0),
        "raw_entity_count_used_as_action_count": False,
        "interpretation": "Les états unavailable/unknown restent mesurés, mais les actions sont priorisées par causes racines et usage réel.",
    }


def _maintenance(report):
    registry = report.get("registry_analysis") or report.get("registry_summary") or {}
    orphan = registry.get("orphan_analysis") or {}
    findings = {str(x.get("rule_id")): x for x in report.get("findings") or [] if isinstance(x, dict)}
    local = findings.get("HD-REG-002") or {}
    coverage = findings.get("HD-CFG-005") or {}
    stale_refs = findings.get("HD-CFG-001") or {}
    return {
        "model": "maintenance_intelligence_v1",
        "orphan_candidates": _int(orphan.get("candidate_count"), 0),
        "probable_orphans": _int(orphan.get("probable_orphan_count"), 0),
        "high_confidence_orphans": _int(orphan.get("high_confidence_count"), 0),
        "local_unavailable_review": _int(local.get("example_count"), 0),
        "missing_reference_count": _int(stale_refs.get("example_count"), 0),
        "automation_coverage_summary": coverage.get("summary"),
        "safe_cleanup_candidates": _int(orphan.get("probable_orphan_count"), 0),
        "automatic_cleanup": False,
    }


def _security(report):
    findings = {str(x.get("rule_id")): x for x in report.get("findings") or [] if isinstance(x, dict)}
    active = findings.get("HD-SEC-001") or {}
    archive = findings.get("HD-SEC-003") or {}
    active_count = _int(active.get("example_count"), 0)
    archive_count = _int(archive.get("example_count"), 0)
    posture = "action_required" if active_count else ("review" if archive_count else "good")
    return {
        "model": "security_posture_v1",
        "posture": posture,
        "active_secret_hint_count": active_count,
        "archive_secret_hint_count": archive_count,
        "secret_values_in_report": False,
        "read_only_validation": True,
    }


def _automation_reliability(report):
    sem = report.get("condition_semantics") or {}
    architecture = report.get("architecture_analysis") or report.get("architecture_summary") or {}
    findings = {str(x.get("rule_id")): x for x in report.get("findings") or [] if isinstance(x, dict)}
    profiles = architecture.get("automation_risk_profiles") or []
    top_profiles = []
    for item in profiles[:12] if isinstance(profiles, list) else []:
        if not isinstance(item, dict):
            continue
        top_profiles.append({key: item.get(key) for key in ("automation", "risk_index", "controls", "triggers", "reads") if key in item})
    return {
        "model": "automation_reliability_v1",
        "automation_count": _int(architecture.get("automation_count"), _int((report.get("inventory") or {}).get("automations_detected"), 0)),
        "physical_controller_pairs_to_review": _int(sem.get("physical_unproven_pair_count"), 0),
        "helper_pairs_to_review": _int(sem.get("helper_unproven_pair_count"), 0),
        "numeric_overlap_candidate_pairs": _int(sem.get("numeric_overlap_candidate_pair_count"), 0),
        "closed_loop_count": _int(architecture.get("closed_loop_count"), 0),
        "long_delay_automation_count": _int((findings.get("HD-AUTO-001") or {}).get("example_count"), 0),
        "single_long_wait_count": _int((findings.get("HD-AUTO-002") or {}).get("example_count"), 0),
        "duplicate_action_count": _int((findings.get("HD-AUTO-005") or {}).get("example_count"), 0),
        "top_risk_profiles": top_profiles,
    }


def _mode_board(items):
    modes = defaultdict(list)
    for item in items:
        domain = str(item.get("domain") or "")
        source_type = str(item.get("source_type") or "")
        source_id = str(item.get("source_id") or "")
        if domain == "security" or source_id.startswith("HD-SEC-"):
            modes["security"].append(item["id"])
        if domain == "automations" or source_id.startswith("HD-AUTO-") or source_id == "HD-RES-001":
            modes["automations"].append(item["id"])
        if source_type.startswith("registry_"):
            modes["external_integrations"].append(item["id"])
        if domain == "configuration" or source_id.startswith("HD-CFG-") or source_id.startswith("HD-REG-"):
            modes["maintenance"].append(item["id"])
        if domain == "performance":
            modes["performance"].append(item["id"])
    for name in ("security", "automations", "external_integrations", "maintenance", "performance"):
        modes.setdefault(name, [])
    return {"model": "doctor_modes_v1", "modes": dict(modes), "automatic_fix": False}


def _coverage(report):
    quality = report.get("quality_gates") or {}
    gates = [x for x in quality.get("gates") or [] if isinstance(x, dict)]
    pass_count = sum(1 for x in gates if x.get("status") == "pass")
    flow = report.get("flow_confidence") or {}
    automation_ratio = _num((report.get("root_cause_summary") or {}).get("automation_coverage_ratio"), 1.0)
    registry = 1.0 if (report.get("registry_analysis") or {}).get("available", True) else 0.0
    gate_ratio = pass_count / len(gates) if gates else 0.0
    score = round(100 * (0.35 * gate_ratio + 0.25 * _num(flow.get("target_resolution_rate"), 0) + 0.25 * automation_ratio + 0.15 * registry))
    return {
        "model": "diagnostic_coverage_v1",
        "score": max(0, min(100, score)),
        "quality_gate_pass_ratio": round(gate_ratio, 3),
        "flow_resolution_ratio": round(_num(flow.get("target_resolution_rate"), 0), 3),
        "automation_coverage_ratio": round(automation_ratio, 3),
        "registry_available": bool(registry),
    }


def _limitations(report):
    return {
        "model": "scan_limitations_v1",
        "items": [
            "Les templates Jinja ne sont pas exécutés ; seules des preuves statiques sont utilisées.",
            "Le scan ne rejoue pas l'historique des traces d'automatisation.",
            "Une intégration cloud hors ligne n'est pas testée depuis Internet par HA Doctor.",
            "Les gains de score sont des projections, pas une garantie après modification.",
            "Aucune correction, suppression, désactivation ou redémarrage n'est effectué automatiquement.",
        ],
        "external_ai_used": False,
        "read_only": True,
    }


def _why_score(report):
    temporal = report.get("temporal_analysis") or {}
    primary = _int((report.get("scores") or {}).get("global"), 0)
    preview = _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), primary)
    resolved = _int(temporal.get("resolved_since_previous_count"), 0)
    delta = _num(temporal.get("score_delta"), 0)
    if delta == 0 and resolved == 0:
        reason = "Aucun diagnostic pénalisant n'a réellement disparu depuis le scan précédent ; le score V4 reste donc stable."
    elif delta == 0:
        reason = "Des changements ont été détectés, mais leur effet arrondi ou contextuel ne modifie pas le score V4."
    else:
        reason = f"Le score V4 a évolué de {delta:+g} point(s) depuis le scan précédent."
    return {
        "model": "score_change_explainer_v1",
        "primary_score": primary,
        "preview_score": preview,
        "score_delta": delta,
        "resolved_since_previous": resolved,
        "reason": reason,
        "v5_preview_not_applied_to_primary": True,
    }


def _domain_next(items):
    grouped = {}
    for item in items:
        domain = str(item.get("domain") or "other")
        if domain not in grouped:
            grouped[domain] = item
    return grouped


def apply_product_intelligence_v2(report):
    if not isinstance(report, dict):
        return report

    base.apply_product_intelligence(report)
    actions = [x for x in (report.get("action_plan") or {}).get("items") or [] if isinstance(x, dict)]
    gains = _gain_map(report)
    normalized = []
    for item in actions:
        x = base.normalize_action(item, gains)
        x["evidence_level"] = evidence_level(item)
        x["risk_breakdown"] = _risk_breakdown(item)
        x["estimated_score_gain"] = round(_num(gains.get(str(item.get("id") or ""), x.get("estimated_score_gain", 0))), 2)
        x["repair_safety"] = (
            "external_manual" if x.get("repair_mode") == "restore_external"
            else "complex_manual" if x.get("repair_mode") in {"logic_review", "guard_dependency"}
            else "manual_low_risk_review"
        )
        normalized.append(x)

    lane_order = {"fix_now": 0, "investigate": 1, "review": 2, "optimize": 3, "watch": 4}
    normalized.sort(key=lambda x: (lane_order.get(x.get("lane"), 9), -_int(x.get("risk_score")), -_num(x.get("estimated_score_gain"))))
    lane_counts = Counter(str(x.get("lane") or "watch") for x in normalized)

    triage = {
        "model": TRIAGE_MODEL,
        "total": len(normalized),
        "lane_counts": {key: lane_counts.get(key, 0) for key in lane_order},
        "next_best_actions": normalized[:10],
        "items": normalized,
        "domain_next_actions": _domain_next(normalized),
        "automatic_fix_available": False,
        "read_only": True,
    }

    trust = dict(report.get("diagnostic_trust") or (report.get("doctor_view") or {}).get("trust") or {})
    trust["model"] = TRUST_MODEL
    coverage = _coverage(report)
    trust["coverage_score"] = coverage["score"]
    if coverage["score"] < 70:
        trust["score"] = min(_int(trust.get("score"), 0), 75)
        trust["level"] = "medium" if _int(trust.get("score"), 0) >= 65 else "low"

    critical_count = _int((report.get("severity_counts") or {}).get("critical"), 0)
    primary = _int((report.get("scores") or {}).get("global"), 0)
    if critical_count or primary < 55:
        verdict = {"code": "critical", "label": "État critique"}
    elif lane_counts.get("fix_now", 0):
        verdict = {"code": "action_required", "label": "Corrections prioritaires"}
    elif lane_counts.get("investigate", 0) or primary < 80:
        verdict = {"code": "needs_attention", "label": "À traiter"}
    elif lane_counts.get("review", 0) or primary < 90:
        verdict = {"code": "monitor", "label": "À surveiller"}
    else:
        verdict = {"code": "healthy", "label": "Bon état"}

    projection = _score_projection(report, normalized)
    health_noise = _health_noise(report)
    maintenance = _maintenance(report)
    security = _security(report)
    reliability = _automation_reliability(report)
    modes = _mode_board(normalized)
    limitations = _limitations(report)
    score_explainer = _why_score(report)

    intelligence = {
        "model": "product_intelligence_v2_engine_candidate",
        "score_projection": projection,
        "entity_noise": health_noise,
        "maintenance": maintenance,
        "security": security,
        "automation_reliability": reliability,
        "doctor_modes": modes,
        "diagnostic_coverage": coverage,
        "score_change_explainer": score_explainer,
        "limitations": limitations,
        "evidence_summary": dict(Counter(x.get("evidence_level") for x in normalized)),
        "safe_automatic_repairs": 0,
        "read_only": True,
    }

    doctor = {
        "model": PRODUCT_MODEL,
        "verdict": verdict,
        "technical_health_score": primary,
        "score_v5_preview": projection["starting_preview_score"],
        "projected_after_top_3": projection["after_top_3"]["score"],
        "next_action": normalized[0] if normalized else None,
        "next_best_actions": normalized[:10],
        "triage_counts": triage["lane_counts"],
        "trust": trust,
        "noise_reduction": health_noise,
        "change_digest": report.get("change_digest") or {},
        "score_projection": projection,
        "coverage": coverage,
        "modes": modes,
        "read_only": True,
        "automatic_fix": False,
        "message": f"{verdict['label']} · {lane_counts.get('fix_now',0)} correction(s) immédiate(s) · confiance {trust.get('score','—')}/100.",
    }

    report["triage_board"] = triage
    report["doctor_view"] = doctor
    report["diagnostic_trust"] = trust
    report["product_intelligence"] = intelligence
    report["share_contract"] = {
        "schema": SHARE_SCHEMA,
        "model": SHARE_MODEL,
        "target_bytes": SHARE_TARGET_BYTES,
        "hard_bytes": SHARE_HARD_BYTES,
        "single_source_of_truth": True,
    }
    report["version"] = VERSION

    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["source"] = "final_correlated_action_plan_v100"
    diagnostic["product_intelligence_model"] = intelligence["model"]

    schema = report.setdefault("report_schema", {})
    schema["version"] = REPORT_SCHEMA
    capabilities = list(schema.get("capabilities") or [])
    for capability in (
        "explainable_risk_breakdown", "evidence_tiers", "multi_horizon_score_projection",
        "entity_noise_model_v1", "maintenance_intelligence_v1", "security_posture_v1",
        "automation_reliability_v1", "doctor_modes_v1", "diagnostic_coverage_v1",
        "score_change_explainer_v1", "scan_limitations_v1", "share_contract_single_source",
        "action_required_verdict", "engine_candidate_product_layer",
    ):
        if capability not in capabilities:
            capabilities.append(capability)
    schema["capabilities"] = capabilities
    return report
