"""HA Doctor 0.8.3 internal report consistency gates."""
from collections import Counter

VERSION = "0.8.3"
MODEL = "consistency_gates_v3"


def _priority_counts(items):
    counts = Counter(str(item.get("priority") or "info") for item in items)
    return {key: counts.get(key, 0) for key in ("action_now", "verify", "optimize", "info")}


def validate_report_consistency_v3(report):
    failures = []
    warnings = []
    plan = report.get("action_plan") or {}
    items = plan.get("items") or []
    queue = report.get("recommendation_queue") or {}
    summary = report.get("diagnostic_summary") or {}
    root = report.get("root_cause_summary") or {}

    if int(plan.get("total", -1) or 0) != len(items):
        failures.append("action_plan.total")
    if int(plan.get("displayed", -1) or 0) != len(items):
        failures.append("action_plan.displayed")
    if int(plan.get("remaining", -1) or 0) != 0:
        failures.append("action_plan.remaining")

    expected_counts = _priority_counts(items)
    for key in ("action_now", "verify", "optimize"):
        if int((plan.get("counts") or {}).get(key, -1) or 0) != expected_counts[key]:
            failures.append(f"action_plan.counts.{key}")
        if int((summary.get("priority_counts") or {}).get(key, -1) or 0) != expected_counts[key]:
            failures.append(f"diagnostic_summary.priority_counts.{key}")

    queue_items = queue.get("items") or []
    if int(queue.get("total", -1) or 0) != len(queue_items):
        failures.append("recommendation_queue.total")
    plan_ids = [str(item.get("id") or "") for item in items]
    queue_ids = [str(item.get("id") or "") for item in queue_items]
    if plan_ids != queue_ids:
        failures.append("recommendation_queue.ids")

    registry_count = sum(
        1 for item in items
        if str(item.get("source_type") or "").startswith("registry_")
    )
    if int(root.get("actionable_registry_incidents", -1) or 0) != registry_count:
        failures.append("root_cause_summary.actionable_registry_incidents")

    score_meta = report.get("score_meta") or {}
    breakdown = score_meta.get("penalty_breakdown") or []
    try:
        summed = round(sum(float(item.get("penalty", 0) or 0) for item in breakdown), 2)
        stated = round(float(score_meta.get("penalty_total", summed) or 0), 2)
        if abs(summed - stated) > 0.15:
            warnings.append("score_meta.penalty_total_cap_or_rounding")
    except Exception:
        warnings.append("score_meta.penalty_breakdown_unreadable")

    privacy = report.get("privacy") or {}
    required_false = (
        "secrets_yaml_read", "raw_states_persisted", "registry_raw_payload_persisted",
        "registry_auth_token_persisted", "automatic_configuration_changes",
        "state_snapshot_persisted", "flow_engine_raw_yaml_persisted",
        "condition_semantics_raw_yaml_persisted", "resilience_raw_yaml_persisted",
    )
    for key in required_false:
        if privacy.get(key) is True:
            failures.append(f"privacy.{key}")

    if str(report.get("version") or "") != VERSION:
        failures.append("report.version")
    schema = str((report.get("report_schema") or {}).get("version") or "")
    if schema and not schema.endswith(VERSION):
        failures.append("report_schema.version")

    result = {
        "model": MODEL,
        "status": "fail" if failures else ("warning" if warnings else "pass"),
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "failures": failures,
        "warnings": warnings,
        "checks": {
            "plan_counts": True,
            "recommendation_queue_identity": True,
            "registry_actionable_count": True,
            "score_penalty_math": True,
            "privacy_invariants": True,
            "version_consistency": True,
        },
    }
    report["consistency_analysis"] = result
    return result
