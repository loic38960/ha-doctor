"""HA Doctor 0.8.5 cross-section consistency gates."""
from collections import Counter

VERSION = "0.8.5"
MODEL = "consistency_gates_v5_cross_section"


def _counts(items):
    counter = Counter(str(item.get("priority") or "info") for item in items)
    return {key: counter.get(key, 0) for key in ("action_now", "verify", "optimize", "info")}


def _int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def validate_report_consistency_v5(report):
    failures = []
    warnings = []
    plan = report.get("action_plan") or {}
    items = plan.get("items") or []
    queue = report.get("recommendation_queue") or {}
    summary = report.get("diagnostic_summary") or {}
    root = report.get("root_cause_summary") or {}
    expected = _counts(items)

    # Final plan / queue identity.
    if _int(plan.get("total", -1), -1) != len(items):
        failures.append("action_plan.total")
    if _int(plan.get("displayed", -1), -1) != len(items):
        failures.append("action_plan.displayed")
    if _int(plan.get("remaining", -1), -1) != 0:
        failures.append("action_plan.remaining")
    for key in ("action_now", "verify", "optimize"):
        if _int((plan.get("counts") or {}).get(key, -1), -1) != expected[key]:
            failures.append(f"action_plan.counts.{key}")
        if _int((summary.get("priority_counts") or {}).get(key, -1), -1) != expected[key]:
            failures.append(f"diagnostic_summary.priority_counts.{key}")

    queue_items = queue.get("items") or []
    if _int(queue.get("total", -1), -1) != len(queue_items):
        failures.append("recommendation_queue.total")
    plan_ids = [str(x.get("id") or "") for x in items]
    queue_ids = [str(x.get("id") or "") for x in queue_items]
    if plan_ids != queue_ids:
        failures.append("recommendation_queue.ids")

    registry_count = sum(1 for item in items if str(item.get("source_type") or "").startswith("registry_"))
    if _int(root.get("actionable_registry_incidents", registry_count), registry_count) != registry_count:
        failures.append("root_cause_summary.actionable_registry_incidents")

    # One scan must describe one state snapshot everywhere.
    inventory = report.get("inventory") or {}
    health = report.get("entity_health") or {}
    if health.get("unavailable"):
        if _int(inventory.get("unavailable_count", -1), -1) != _int((health.get("unavailable") or {}).get("total", -2), -2):
            failures.append("state_snapshot.unavailable_count")
    if health.get("unknown"):
        if _int(inventory.get("unknown_count", -1), -1) != _int((health.get("unknown") or {}).get("total", -2), -2):
            failures.append("state_snapshot.unknown_count")

    # Flow metadata must describe the final promoted graph, not an earlier pass.
    flow = report.get("flow_confidence") or {}
    meta = report.get("dependency_graph_meta") or {}
    if _int(meta.get("low_confidence_dynamic_edges", -1), -1) != _int(flow.get("low_confidence_dynamic_edges", -2), -2):
        failures.append("flow.low_confidence_dynamic_edges")
    if _int(meta.get("review_required_dynamic_edges", -1), -1) != _int(flow.get("review_required_dynamic_edges", -2), -2):
        failures.append("flow.review_required_dynamic_edges")
    if str(meta.get("confidence_model") or "") != str(flow.get("model") or ""):
        failures.append("flow.confidence_model")

    architecture = report.get("architecture_analysis") or {}
    if not architecture.get("post_flow_recomputed"):
        failures.append("architecture.post_flow_recomputed")
    if not str(architecture.get("model") or "").startswith("architecture_v3"):
        warnings.append("architecture.model")

    # Executive metrics are user-facing: stale values are a report failure.
    executive = report.get("executive_summary") or {}
    metric_pairs = (
        ("shared_actuator_count", "shared_actuator_count"),
        ("closed_loop_count", "closed_loop_count"),
        ("critical_dependency_count", "critical_dependency_count"),
    )
    for executive_key, architecture_key in metric_pairs:
        if executive_key in executive and architecture_key in architecture:
            if _int(executive.get(executive_key), -1) != _int(architecture.get(architecture_key), -2):
                failures.append(f"executive_summary.{executive_key}")

    # Controller counts must describe the actual remaining pair list.
    sem = report.get("condition_semantics") or {}
    unproven = sem.get("unproven_pairs") or []
    physical = sum(1 for item in unproven if str(item.get("target_kind") or "") == "actuator")
    if unproven and not physical:
        # Older entries may not carry target_kind; infer from architecture domain
        # by comparing with the stored count rather than fabricating a kind.
        physical = None
    if physical is not None and _int(sem.get("physical_unproven_pair_count", physical), physical) != physical:
        failures.append("condition_semantics.physical_unproven_pair_count")
    if _int(sem.get("unproven_pair_count", len(unproven)), len(unproven)) != len(unproven):
        failures.append("condition_semantics.unproven_pair_count")

    finding = next((x for x in report.get("findings") or [] if x.get("rule_id") == "HD-AUTO-003"), None)
    if finding:
        finding_pairs = sum(_int(example.get("unprotected_pair_count", 0), 0) for example in finding.get("examples") or [])
        # The finding intentionally shows only examples, so require equality only
        # when all remaining pairs fit inside the untruncated example set.
        if len(unproven) <= 60 and finding_pairs != len(unproven):
            failures.append("condition_semantics.finding_pair_count")

    # Temporal resolved and de-escalated sets must remain disjoint and grounded.
    temporal = report.get("temporal_analysis") or {}
    current_diag_ids = {
        str(item.get("id") or "")
        for item in report.get("diagnostic_explanations") or []
        if item.get("id")
    }
    resolved = {str(x) for x in temporal.get("resolved_since_previous") or []}
    deescalated = {str(x) for x in temporal.get("deescalated_since_previous") or []}
    if resolved & current_diag_ids:
        failures.append("temporal.false_resolved")
    if any(x not in current_diag_ids for x in deescalated):
        failures.append("temporal.false_deescalated")
    if resolved & deescalated:
        failures.append("temporal.resolved_deescalated_overlap")

    lineage = report.get("entity_lineage") or {}
    if lineage.get("raw_yaml_persisted") is True or lineage.get("secret_values_persisted") is True:
        failures.append("lineage.privacy")
    if _int(lineage.get("parse_error_count", 0), 0) > 0:
        warnings.append("lineage.parse_errors")

    # Score maths and preview projections must remain explainable and bounded.
    score_meta = report.get("score_meta") or {}
    breakdown = score_meta.get("penalty_breakdown") or []
    try:
        summed = round(sum(_float(item.get("penalty", 0), 0.0) for item in breakdown), 2)
        stated = round(_float(score_meta.get("penalty_total", summed), summed), 2)
        if abs(summed - stated) > 0.15:
            warnings.append("score_meta.penalty_total_cap_or_rounding")
    except Exception:
        warnings.append("score_meta.penalty_breakdown_unreadable")

    v5 = report.get("score_v5_preview") or {}
    if v5:
        raw = _float(v5.get("v5_preview_score_raw", 0), -1)
        rounded = _int(v5.get("v5_preview_score", -1), -1)
        projected = _int(v5.get("projected_after_top_3_fixes", rounded), -1)
        if not (0 <= raw <= 100 and 0 <= rounded <= 100 and 0 <= projected <= 100):
            failures.append("score_v5.bounds")
        if rounded != int(round(raw)):
            failures.append("score_v5.rounding")
        if projected < rounded:
            failures.append("score_v5.projection_direction")
        v5_breakdown = v5.get("why_lost_points") or []
        if any(_float(x.get("usage_factor", 1.0), 1.0) <= 0 for x in v5_breakdown):
            failures.append("score_v5.usage_factor")

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
            "single_state_snapshot_identity": True,
            "flow_metadata_identity": True,
            "architecture_post_flow": True,
            "executive_architecture_identity": True,
            "condition_semantics_identity": True,
            "temporal_resolution_semantics": True,
            "lineage_privacy": True,
            "score_penalty_math": True,
            "score_v5_projection_math": True,
            "privacy_invariants": True,
            "version_consistency": True,
        },
    }
    report["consistency_analysis"] = result
    return result
