"""HA Doctor 0.9 product-facing triage and decision layer.

This module consumes the already redacted/read-only diagnostic report. It does
not query Home Assistant, execute templates, or change the primary Score V4.
Its job is to turn a technically rich report into a short, deterministic answer
to: what matters, what should be done first, and how trustworthy is this scan?
"""
from collections import Counter

VERSION = "0.9.0"
REPORT_SCHEMA = "ha-doctor-report/0.9"
MODEL = "doctor_view_v1"
TRIAGE_MODEL = "triage_board_v1"
TRUST_MODEL = "diagnostic_trust_v1"

_PRIORITY_WEIGHT = {"action_now": 40, "verify": 24, "optimize": 10, "info": 2}
_SEVERITY_WEIGHT = {"critical": 32, "high": 25, "medium": 16, "low": 7, "info": 1}
_IMPACT_WEIGHT = {"critical": 16, "high": 12, "medium": 7, "low": 3, "none": 0}
_LANE_ORDER = {"fix_now": 0, "investigate": 1, "review": 2, "optimize": 3, "watch": 4}


def _number(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def confidence_tier(score):
    score = _number(score, 0)
    if score >= 0.90:
        return "A"
    if score >= 0.75:
        return "B"
    if score >= 0.60:
        return "C"
    return "D"


def customer_lane(item):
    priority = str(item.get("priority") or "info")
    severity = str(item.get("severity") or "info")
    if priority == "action_now":
        return "fix_now"
    if priority == "verify" and severity in {"critical", "high", "medium"}:
        return "investigate"
    if priority == "verify":
        return "review"
    if priority == "optimize":
        return "optimize"
    return "watch"


def repair_mode(item):
    source_type = str(item.get("source_type") or "")
    source_id = str(item.get("source_id") or item.get("rule_id") or "")
    domain = str(item.get("domain") or "")
    if source_type.startswith("registry_"):
        return "restore_external"
    if source_id == "HD-AUTO-003":
        return "logic_review"
    if source_id == "HD-RES-001":
        return "guard_dependency"
    if source_id.startswith("HD-SEC-") or source_id.startswith("HD-CFG-"):
        return "manual_config"
    if source_id.startswith("HD-AUTO-") or domain == "automations":
        return "automation_cleanup"
    return "manual_review"


def effort_class(item):
    mode = repair_mode(item)
    if mode == "restore_external":
        return "external"
    if mode in {"logic_review", "guard_dependency"}:
        return "complex"
    if str(item.get("priority") or "") == "action_now":
        return "small_or_medium"
    return "small"


def risk_score(item):
    priority = str(item.get("priority") or "info")
    severity = str(item.get("severity") or "info")
    confidence = _number(item.get("confidence_score"), 0.5)
    impact = item.get("dependency_impact") or {}
    impact_level = str(impact.get("level") or "none")
    temporal = item.get("temporal") or {}
    temporal_status = str(temporal.get("status") or "")
    temporal_bonus = 6 if temporal_status == "persistent" else (3 if temporal_status == "recurrent" else 0)
    score = (
        _PRIORITY_WEIGHT.get(priority, 0)
        + _SEVERITY_WEIGHT.get(severity, 0)
        + _IMPACT_WEIGHT.get(impact_level, 0)
        + temporal_bonus
        + round(confidence * 6)
    )
    return max(0, min(100, int(score)))


def _fix_gain_map(report):
    result = {}
    for item in (report.get("score_v5_preview") or {}).get("fix_scenarios") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        result[str(item["id"])] = round(_number(item.get("estimated_gain"), 0), 2)
    return result


def _first_check(item):
    first = item.get("first_check") or {}
    if not isinstance(first, dict):
        return None
    if not first.get("title") and not first.get("detail"):
        return None
    return {
        "title": first.get("title"),
        "detail": first.get("detail"),
    }


def normalize_action(item, gain_map=None):
    gain_map = gain_map or {}
    diagnostic_id = str(item.get("id") or "")
    impact = item.get("dependency_impact") or {}
    temporal = item.get("temporal") or {}
    normalized = {
        "id": diagnostic_id,
        "title": item.get("title"),
        "priority": item.get("priority"),
        "severity": item.get("severity"),
        "domain": item.get("domain"),
        "source_type": item.get("source_type"),
        "source_id": item.get("source_id"),
        "confidence": item.get("confidence"),
        "confidence_score": round(_number(item.get("confidence_score"), 0), 3),
        "confidence_tier": confidence_tier(item.get("confidence_score")),
        "lane": customer_lane(item),
        "repair_mode": repair_mode(item),
        "effort": effort_class(item),
        "risk_score": risk_score(item),
        "estimated_score_gain": round(_number(gain_map.get(diagnostic_id), 0), 2),
        "dependency_impact": str(impact.get("level") or "none"),
        "impacted_automation_count": int(impact.get("impacted_automation_count", 0) or 0),
        "temporal_status": temporal.get("status"),
        "first_check": _first_check(item),
    }
    return normalized


def build_triage_board(report):
    items = [item for item in (report.get("action_plan") or {}).get("items") or [] if isinstance(item, dict)]
    gain_map = _fix_gain_map(report)
    normalized = [normalize_action(item, gain_map) for item in items]
    normalized.sort(key=lambda item: (
        _LANE_ORDER.get(item["lane"], 9),
        -item["risk_score"],
        -item["estimated_score_gain"],
        str(item.get("title") or ""),
    ))
    lane_counts = Counter(item["lane"] for item in normalized)
    source_counts = Counter(str(item.get("source_type") or "unknown") for item in normalized)
    return {
        "model": TRIAGE_MODEL,
        "total": len(normalized),
        "lane_counts": {key: lane_counts.get(key, 0) for key in _LANE_ORDER},
        "source_type_counts": dict(source_counts),
        "next_best_actions": normalized[:7],
        "items": normalized,
        "automatic_fix_available": False,
        "read_only": True,
    }


def _trust_summary(report):
    quality = report.get("quality_gates") or {}
    consistency = report.get("consistency_analysis") or {}
    flow = report.get("flow_confidence") or {}
    lineage = report.get("entity_lineage") or {}
    snapshot = report.get("snapshot_consistency") or report.get("state_snapshot") or {}
    privacy = report.get("privacy") or {}

    quality_overall = str(quality.get("overall") or "warning")
    consistency_status = str(consistency.get("status") or "warning")
    flow_status = str(flow.get("quality_status") or "warning")
    parse_errors = int(lineage.get("parse_error_count", 0) or 0)
    unresolved = int(flow.get("unresolved_dynamic_targets", 0) or 0)

    deductions = 0
    reasons = []
    if quality_overall == "fail":
        deductions += 35
        reasons.append("quality_gate_failure")
    elif quality_overall == "warning":
        deductions += 10
    if consistency_status == "fail":
        deductions += 35
        reasons.append("internal_consistency_failure")
    elif consistency_status != "pass":
        deductions += 8
    if flow_status == "fail":
        deductions += 20
        reasons.append("flow_failure")
    elif flow_status == "warning":
        deductions += 6
    if parse_errors:
        deductions += min(15, parse_errors * 3)
        reasons.append("lineage_parse_errors")
    if unresolved:
        deductions += min(15, unresolved * 2)
        reasons.append("unresolved_dynamic_targets")

    score = max(0, 100 - deductions)
    level = "high" if score >= 85 else ("medium" if score >= 65 else "low")
    one_snapshot = bool(
        privacy.get("single_ephemeral_state_snapshot")
        or snapshot.get("single_snapshot")
        or snapshot.get("network_reads") == 1
        or privacy.get("state_snapshot_ephemeral")
    )
    return {
        "model": TRUST_MODEL,
        "score": score,
        "level": level,
        "quality_overall": quality_overall,
        "consistency_status": consistency_status,
        "flow_status": flow_status,
        "lineage_parse_error_count": parse_errors,
        "unresolved_dynamic_target_count": unresolved,
        "read_only": not bool(privacy.get("automatic_configuration_changes", False)),
        "single_snapshot_evidence": one_snapshot,
        "raw_states_persisted": False,
        "raw_yaml_persisted": False,
        "secret_values_persisted": False,
        "external_ai_used": False,
        "deduction_reasons": reasons,
    }


def _noise_summary(report, plan_count):
    explanations = [item for item in report.get("diagnostic_explanations") or [] if isinstance(item, dict)]
    findings = [item for item in report.get("findings") or [] if isinstance(item, dict)]
    total = len(explanations) if explanations else len(findings)
    outside = max(0, total - plan_count)
    compression = round(outside / total, 3) if total else 0.0
    return {
        "detected_diagnostics": total,
        "action_plan_diagnostics": plan_count,
        "kept_outside_plan": outside,
        "noise_or_observation_compression_ratio": compression,
        "raw_entity_noise_not_used_as_action_count": True,
    }


def _change_digest(report):
    temporal = report.get("temporal_analysis") or {}
    regression = report.get("regression_analysis") or {}
    return {
        "model": "change_digest_v1",
        "new": int(temporal.get("new_count", 0) or 0),
        "persistent": int(temporal.get("persistent_count", 0) or 0),
        "recurrent": int(temporal.get("recurrent_count", 0) or 0),
        "resolved": int(temporal.get("resolved_since_previous_count", 0) or 0),
        "deescalated": int(temporal.get("deescalated_since_previous_count", 0) or 0),
        "score_delta": regression.get("score_delta", temporal.get("score_delta")),
        "trend": regression.get("state", temporal.get("trend_state", "unknown")),
        "requires_attention": bool(regression.get("requires_attention", False)),
    }


def _verdict(report, triage, trust):
    lanes = triage.get("lane_counts") or {}
    score = int((report.get("scores") or {}).get("global", 0) or 0)
    critical_count = int((report.get("severity_counts") or {}).get("critical", 0) or 0)
    if critical_count or lanes.get("fix_now", 0) >= 3 or score < 60:
        code = "critical"
        label = "Corrections prioritaires"
    elif lanes.get("fix_now", 0) or lanes.get("investigate", 0) or score < 80:
        code = "needs_attention"
        label = "À traiter"
    elif lanes.get("review", 0) or trust.get("level") != "high" or score < 90:
        code = "monitor"
        label = "À surveiller"
    else:
        code = "healthy"
        label = "Bon état"
    return {"code": code, "label": label}


def _projection(report, triage):
    preview = report.get("score_v5_preview") or {}
    primary = int((report.get("scores") or {}).get("global", 0) or 0)
    projected = int(preview.get("projected_after_top_3_fixes", primary) or primary)
    next_actions = triage.get("next_best_actions") or []
    known_gain = round(sum(_number(item.get("estimated_score_gain"), 0) for item in next_actions[:3]), 2)
    return {
        "technical_score_v4": primary,
        "score_v5_preview": int(preview.get("v5_preview_score", primary) or primary),
        "projected_after_top_3": projected,
        "known_top_3_gain": known_gain,
        "primary_score_mutated": False,
    }


def apply_product_intelligence(report):
    if not isinstance(report, dict):
        return report

    triage = build_triage_board(report)
    trust = _trust_summary(report)
    noise = _noise_summary(report, triage["total"])
    changes = _change_digest(report)
    verdict = _verdict(report, triage, trust)
    projection = _projection(report, triage)
    top = triage.get("next_best_actions") or []

    doctor = {
        "model": MODEL,
        "verdict": verdict,
        "technical_health_score": projection["technical_score_v4"],
        "score_v5_preview": projection["score_v5_preview"],
        "projected_after_top_3": projection["projected_after_top_3"],
        "next_action": top[0] if top else None,
        "next_best_actions": top,
        "triage_counts": triage.get("lane_counts") or {},
        "trust": trust,
        "noise_reduction": noise,
        "change_digest": changes,
        "projection": projection,
        "read_only": True,
        "automatic_fix": False,
        "message": (
            f"{verdict['label']} · {triage['lane_counts'].get('fix_now',0)} à corriger maintenant, "
            f"{triage['lane_counts'].get('investigate',0)} à investiguer, "
            f"confiance diagnostic {trust['score']}/100."
        ),
    }

    report["triage_board"] = triage
    report["doctor_view"] = doctor
    report["diagnostic_trust"] = trust
    report["change_digest"] = changes
    report["version"] = VERSION

    schema = report.get("report_schema") or {}
    compatible = list(schema.get("backward_compatible_with") or [])
    if "0.8.8" not in compatible:
        compatible.append("0.8.8")
    capabilities = list(schema.get("capabilities") or [])
    for capability in (
        "doctor_view_v1",
        "customer_triage_board_v1",
        "risk_ranked_next_best_actions",
        "diagnostic_trust_v1",
        "noise_compression_metrics",
        "change_digest_v1",
        "fix_projection_summary",
        "milestone_release_model",
    ):
        if capability not in capabilities:
            capabilities.append(capability)
    report["report_schema"] = {
        **schema,
        "version": REPORT_SCHEMA,
        "backward_compatible_with": compatible,
        "capabilities": capabilities,
    }

    report.setdefault("diagnostic_engine", {}).update({
        "version": "product_triage_v1",
        "doctor_view": True,
        "triage_board": True,
        "diagnostic_trust": True,
        "external_ai_used": False,
        "automatic_fix": False,
        "read_only": True,
    })
    report.setdefault("privacy", {}).update({
        "automatic_configuration_changes": False,
        "product_layer_additional_state_reads": 0,
        "product_layer_raw_states_persisted": False,
        "product_layer_raw_yaml_persisted": False,
        "product_layer_secret_values_persisted": False,
    })
    report.setdefault("score_meta", {}).update({
        "delivery_version": VERSION,
        "product_layer": MODEL,
        "score_v4_primary_unchanged_by_v090": True,
    })
    return report
