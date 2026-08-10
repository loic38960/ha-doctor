"""HA Doctor 0.8.4 internal consistency gates."""
from collections import Counter

VERSION = "0.8.4"
MODEL = "consistency_gates_v4"


def _counts(items):
    counter = Counter(str(item.get("priority") or "info") for item in items)
    return {key: counter.get(key, 0) for key in ("action_now", "verify", "optimize", "info")}


def validate_report_consistency_v4(report):
    failures = []
    warnings = []
    plan = report.get("action_plan") or {}
    items = plan.get("items") or []
    queue = report.get("recommendation_queue") or {}
    summary = report.get("diagnostic_summary") or {}
    root = report.get("root_cause_summary") or {}
    expected = _counts(items)

    if int(plan.get("total", -1) or 0) != len(items):
        failures.append("action_plan.total")
    if int(plan.get("displayed", -1) or 0) != len(items):
        failures.append("action_plan.displayed")
    if int(plan.get("remaining", -1) or 0) != 0:
        failures.append("action_plan.remaining")
    for key in ("action_now", "verify", "optimize"):
        if int((plan.get("counts") or {}).get(key, -1) or 0) != expected[key]:
            failures.append(f"action_plan.counts.{key}")
        if int((summary.get("priority_counts") or {}).get(key, -1) or 0) != expected[key]:
            failures.append(f"diagnostic_summary.priority_counts.{key}")

    queue_items = queue.get("items") or []
    if int(queue.get("total", -1) or 0) != len(queue_items):
        failures.append("recommendation_queue.total")
    if [str(x.get("id") or "") for x in items] != [str(x.get("id") or "") for x in queue_items]:
        failures.append("recommendation_queue.ids")

    registry_count = sum(1 for item in items if str(item.get("source_type") or "").startswith("registry_"))
    if int(root.get("actionable_registry_incidents", registry_count) or 0) != registry_count:
        failures.append("root_cause_summary.actionable_registry_incidents")

    flow = report.get("flow_confidence") or {}
    meta = report.get("dependency_graph_meta") or {}
    if int(meta.get("low_confidence_dynamic_edges", -1) or 0) != int(flow.get("low_confidence_dynamic_edges", -2) or 0):
        failures.append("flow.low_confidence_dynamic_edges")
    if int(meta.get("review_required_dynamic_edges", -1) or 0) != int(flow.get("review_required_dynamic_edges", -2) or 0):
        failures.append("flow.review_required_dynamic_edges")
    if str(meta.get("confidence_model") or "") != str(flow.get("model") or ""):
        failures.append("flow.confidence_model")

    architecture = report.get("architecture_analysis") or {}
    if not architecture.get("post_flow_recomputed"):
        failures.append("architecture.post_flow_recomputed")
    if not str(architecture.get("model") or "").startswith("architecture_v3"):
        warnings.append("architecture.model")

    temporal = report.get("temporal_analysis") or {}
    current_diag_ids = {
        str(item.get("id") or "")
        for item in report.get("diagnostic_explanations") or []
        if item.get("id")
    }
    if any(str(diagnostic_id) in current_diag_ids for diagnostic_id in temporal.get("resolved_since_previous") or []):
        failures.append("temporal.false_resolved")
    if any(str(diagnostic_id) not in current_diag_ids for diagnostic_id in temporal.get("deescalated_since_previous") or []):
        failures.append("temporal.false_deescalated")

    lineage = report.get("entity_lineage") or {}
    if lineage.get("raw_yaml_persisted") is True or lineage.get("secret_values_persisted") is True:
        failures.append("lineage.privacy")
    if int(lineage.get("parse_error_count", 0) or 0) > 0:
        warnings.append("lineage.parse_errors")

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
        "entity_lineage_raw_yaml_persisted", "entity_lineage_secret_values_persisted",
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
            "flow_metadata_identity": True,
            "architecture_post_flow": True,
            "temporal_resolution_semantics": True,
            "lineage_privacy": True,
            "score_penalty_math": True,
            "privacy_invariants": True,
            "version_consistency": True,
        },
    }
    report["consistency_analysis"] = result
    return result
