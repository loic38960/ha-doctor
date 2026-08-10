"""HA Doctor 0.8.7 assistant handoff report.

The local full report remains untouched. The V2 handoff is intentionally hard
bounded so it can be pasted or attached to a support/assistant conversation
without reproducing large registry, architecture and graph payloads.
"""
import json

VERSION = "0.8.7"
MODEL = "assistant_share_report_v2"
SCHEMA = "ha-doctor-share/2"
TARGET_BYTES = 32_000
HARD_BYTES = 36_000
TEXT_LIMIT = 420


def _pick(source, keys):
    if not isinstance(source, dict):
        return {}
    return {key: source.get(key) for key in keys if key in source}


def _text(value, limit=TEXT_LIMIT):
    if value is None:
        return None
    value = str(value)
    return value if len(value) <= limit else value[:limit] + "…"


def _trim(value, max_items=4, depth=0, text_limit=TEXT_LIMIT):
    if depth > 5:
        return None
    if isinstance(value, str):
        return _text(value, text_limit)
    if isinstance(value, list):
        return [
            _trim(item, max_items=max_items, depth=depth + 1, text_limit=text_limit)
            for item in value[:max_items]
        ]
    if isinstance(value, dict):
        return {
            key: _trim(item, max_items=max_items, depth=depth + 1, text_limit=text_limit)
            for key, item in value.items()
        }
    return value


def _json_size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _compact_example(value, level):
    return _trim(value, max_items=3 if level == 0 else 2, text_limit=320 if level == 0 else 220)


def _compact_finding(item, level):
    result = _pick(item, (
        "rule_id", "title", "severity", "domain", "priority", "priority_label",
    ))
    result["summary"] = _text(item.get("summary"), 360 if level == 0 else 240)
    if level == 0 or item.get("priority") == "action_now":
        result["recommendation"] = _text(item.get("recommendation"), 320 if level == 0 else 220)

    examples = item.get("examples") or []
    if examples:
        if item.get("priority") == "action_now":
            limit = 3 if level == 0 else 2
        elif item.get("severity") in {"critical", "high", "medium"}:
            limit = 2 if level == 0 else 1
        else:
            limit = 1 if level == 0 else 0
        if limit:
            result["examples"] = [_compact_example(example, level) for example in examples[:limit]]
        result["example_count"] = len(examples)
    return result


def _compact_action(item, level):
    result = _pick(item, (
        "id", "title", "priority", "severity", "domain", "confidence",
        "confidence_score", "source_type", "source_id",
    ))
    first = item.get("first_check") or {}
    if first:
        result["first_check"] = {
            "title": _text(first.get("title"), 180),
            "detail": _text(first.get("detail"), 220 if level == 0 else 150),
        }
    temporal = item.get("temporal") or {}
    if temporal:
        result["temporal"] = _pick(temporal, (
            "status", "occurrences", "qualified_observations", "first_seen",
            "last_seen_before_current", "persistence_factor",
        ))
    impact = item.get("dependency_impact") or {}
    if impact:
        result["dependency_impact"] = _pick(impact, (
            "level", "impacted_automation_count", "high_risk_automation_count",
            "weighted_impact_score", "lineage_used",
        ))
    if item.get("source_id") == "HD-AUTO-003" and item.get("controller_review_summary"):
        result["controller_review_summary"] = _pick(
            item["controller_review_summary"],
            ("entity_count", "pair_count", "physical_pair_count", "helper_pair_count"),
        )
    return result


def _compact_observation(item):
    return {
        **_pick(item, (
            "id", "title", "priority", "severity", "domain", "confidence_score",
            "source_type", "source_id",
        )),
        "diagnosis": _text(item.get("diagnosis"), 220),
        "temporal": _pick(item.get("temporal") or {}, ("status", "occurrences", "first_seen")),
    }


def _health_summary(report, level):
    health = report.get("entity_health") or {}
    result = {}
    for key in ("unavailable", "unknown"):
        section = health.get(key) or {}
        groups = []
        for group in (section.get("groups") or [])[:8 if level == 0 else 6]:
            entry = _pick(group, ("key", "label", "count"))
            examples = group.get("examples") or []
            if examples:
                entry["examples"] = examples[:3 if level == 0 else 2]
            groups.append(entry)
        result[key] = {
            **_pick(section, (
                "total", "stateful_count", "ignored_stateless_count",
                "likely_transient_count", "likely_optional_count",
                "attention_count", "review_count",
            )),
            "groups": groups,
        }
    return result


def _registry_actionable_summary(report, level):
    registry = report.get("registry_analysis") or {}
    plan_items = (report.get("action_plan") or {}).get("items") or []
    integration_ids = {
        str(item.get("source_id"))
        for item in plan_items
        if isinstance(item, dict) and item.get("source_type") == "registry_integration"
    }
    device_ids = {
        str(item.get("source_id"))
        for item in plan_items
        if isinstance(item, dict) and item.get("source_type") == "registry_device"
    }
    cluster_ids = {
        str(item.get("source_id"))
        for item in plan_items
        if isinstance(item, dict) and item.get("source_type") == "registry_cluster"
    }

    def compact_group(item, kind):
        identity_key = "integration" if kind == "integration" else "name"
        result = _pick(item, (
            identity_key, "manufacturer", "model", "total", "core_total",
            "core_affected", "healthy", "unavailable", "unknown",
            "affected_ratio", "status", "contextual_status", "context_factor",
        ))
        examples = item.get("examples") or []
        if examples:
            result["examples"] = examples[:3 if level == 0 else 2]
        return result

    integration = registry.get("integration_health") or {}
    device = registry.get("device_health") or {}
    integration_groups = [
        compact_group(item, "integration")
        for item in (integration.get("groups") or [])
        if str(item.get("integration")) in integration_ids
    ]
    device_groups = [
        compact_group(item, "device")
        for item in (device.get("groups") or [])
        if str(item.get("name")) in device_ids
    ]

    observations = [
        item for item in (report.get("diagnostic_explanations") or [])
        if isinstance(item, dict)
        and item.get("source_type") == "registry_cluster"
        and (
            str(item.get("source_id")) in cluster_ids
            or item.get("priority") == "info"
        )
    ]

    return {
        "available": registry.get("available"),
        "entity_registry_count": registry.get("entity_registry_count"),
        "device_registry_count": registry.get("device_registry_count"),
        "integration_totals": _pick(integration, ("total", "affected", "offline", "problematic")),
        "device_totals": _pick(device, ("total", "affected", "offline", "problematic")),
        "actionable_integrations": integration_groups,
        "actionable_devices": device_groups,
        "contextual_clusters": [
            _pick(item, ("id", "title", "priority", "source_id"))
            for item in observations[:4]
        ],
        "orphan_analysis": _pick(registry.get("orphan_analysis") or {}, (
            "candidate_count", "high_confidence_count", "probable_orphan_count",
            "review_candidate_count",
        )),
    }


def _architecture_summary(report, level):
    architecture = report.get("architecture_analysis") or {}
    hotspots = []
    for item in (architecture.get("top_hotspots") or [])[:6 if level == 0 else 4]:
        entry = _pick(item, (
            "entity_id", "kind", "criticality", "triggered_automations",
            "controlling_automations", "reading_automations",
            "referencing_automations", "average_control_confidence",
        ))
        controllers = item.get("controllers") or []
        triggers = item.get("triggers") or []
        if controllers:
            entry["controller_examples"] = controllers[:3]
        if triggers:
            entry["trigger_examples"] = triggers[:2]
        hotspots.append(entry)

    critical = [
        _pick(item, (
            "entity_id", "kind", "criticality", "triggered_automations",
            "reading_automations", "referencing_automations",
        ))
        for item in (architecture.get("critical_dependencies") or [])[:6]
    ]
    return {
        **_pick(architecture, (
            "model", "complexity_score", "complexity_label", "automation_count",
            "entity_dependency_count", "entity_edge_count", "control_edge_count",
            "call_edge_count", "shared_actuator_count", "helper_hub_count",
            "trigger_hub_count", "call_hub_count", "critical_dependency_count",
            "closed_loop_count", "physical_unproven_controller_pair_count",
            "helper_unproven_controller_pair_count",
            "branch_protocol_resolved_pair_count",
        )),
        "top_hotspots": hotspots,
        "critical_dependencies": critical,
    }


def _semantics_summary(report, level):
    sem = report.get("condition_semantics") or {}
    result = {
        **_pick(sem, (
            "model", "controller_pairs_analyzed", "proven_exclusive_pair_count",
            "coordinated_pair_count", "resolved_pair_count", "unproven_pair_count",
            "physical_unproven_pair_count", "helper_unproven_pair_count",
            "other_unproven_pair_count", "protocol_coordinated_pair_count",
            "branch_protocol_resolved_pair_count",
        )),
        "unproven_pairs": [
            _pick(item, ("entity_id", "automations", "target_kind", "review_priority"))
            for item in (sem.get("unproven_pairs") or [])[:12]
        ],
    }
    if level == 0:
        result["branch_protocol_resolved_pairs"] = [
            _pick(item, ("entity_id", "automations", "reason", "target_kind", "confidence"))
            for item in (sem.get("branch_protocol_resolved_pairs") or [])[:6]
        ]
    return result


def _resilience_summary(report):
    analysis = report.get("resilience_analysis") or {}
    recommendations = report.get("resilience_recommendations") or {}
    return {
        "analysis": {
            **_pick(analysis, (
                "model", "critical_dependency_count", "external_spof_count",
                "helper_dependency_count", "review_count", "partial_count",
                "protected_count", "configuration_dependency_count",
                "numeric_default_only_count", "unprotected_automation_count",
            )),
            "items": [
                _pick(item, (
                    "entity_id", "criticality", "automation_count",
                    "explicit_guard_count", "numeric_default_only_count",
                    "unprotected_count", "status", "counts_as_external_spof",
                ))
                for item in (analysis.get("items") or [])[:8]
            ],
        },
        "recommendations": {
            **_pick(recommendations, ("model", "count", "action_plan_diagnostic_id")),
            "items": [
                {
                    **_pick(item, (
                        "entity_id", "criticality", "automation_count",
                        "explicit_guard_count", "numeric_default_only_count",
                        "unprotected_count",
                    )),
                    "unprotected_automations": (item.get("unprotected_automations") or [])[:6],
                }
                for item in (recommendations.get("items") or [])[:4]
            ],
        },
    }


def _temporal_summary(report):
    temporal = report.get("temporal_analysis") or {}
    return _pick(temporal, (
        "enabled", "model", "history_limit", "scan_count", "previous_score",
        "score_delta", "new_count", "persistent_count",
        "resolved_since_previous_count", "recurrent_count",
        "deescalated_since_previous_count", "all_diagnostic_count",
        "action_plan_diagnostic_count", "rapid_rescan_protection",
        "rapid_rescans_promote_persistence", "minimum_persistence_interval_seconds",
    )) | {
        "new_ids": (temporal.get("new_ids") or [])[:12],
        "resolved_since_previous": (temporal.get("resolved_since_previous") or [])[:12],
        "deescalated_since_previous": (temporal.get("deescalated_since_previous") or [])[:12],
    }


def _quality_summary(report):
    quality = report.get("quality_gates") or {}
    gates = [
        _pick(item, ("key", "label", "status", "detail"))
        for item in (quality.get("gates") or [])
        if item.get("status") != "pass"
    ]
    consistency = report.get("consistency_analysis") or {}
    return {
        "quality_gates": {
            "model": quality.get("model"),
            "overall": quality.get("overall"),
            "counts": quality.get("counts") or {},
            "non_pass_gates": gates,
        },
        "consistency": _pick(consistency, (
            "model", "status", "failure_count", "warning_count", "failures", "warnings",
        )),
    }


def _score_preview(report, level):
    score = report.get("score_v5_preview") or {}
    why = [
        _pick(item, (
            "id", "title", "technical_penalty", "v5_penalty", "context_factor",
            "persistence_factor", "usage_factor", "usage_reason",
            "blast_radius", "impacted_automation_count",
        ))
        for item in (score.get("why_lost_points") or [])[:8 if level == 0 else 6]
    ]
    fixes = [
        _pick(item, ("rank", "id", "title", "estimated_gain", "projected_score_after_fix"))
        for item in (score.get("fix_scenarios") or [])[:5]
    ]
    return {
        **_pick(score, (
            "model", "technical_v4_score", "v5_preview_score",
            "v5_preview_score_raw", "delta_vs_v4", "technical_penalty_total",
            "v5_penalty_total", "top_3_fix_estimated_gain",
            "projected_after_top_3_fixes", "applied_to_primary_score",
            "usage_aware",
        )),
        "why_lost_points": why,
        "fix_scenarios": fixes,
    }


def _build(report, level):
    plan = report.get("action_plan") or {}
    plan_items = [item for item in (plan.get("items") or []) if isinstance(item, dict)]
    plan_ids = {str(item.get("id")) for item in plan_items if item.get("id")}
    observations = [
        item for item in (report.get("diagnostic_explanations") or [])
        if isinstance(item, dict) and str(item.get("id") or "") not in plan_ids
    ]

    executive = report.get("executive_summary") or {}
    diagnostic = report.get("diagnostic_summary") or {}
    inventory = report.get("inventory") or {}
    lineage = report.get("entity_lineage") or {}

    result = {
        "product": report.get("product"),
        "version": report.get("version"),
        "generated_at": report.get("generated_at"),
        "scan_duration_seconds": report.get("scan_duration_seconds"),
        "scores": report.get("scores") or {},
        "severity_counts": report.get("severity_counts") or {},
        "share_schema": {
            "version": SCHEMA,
            "model": MODEL,
            "source_report_version": report.get("version"),
            "target_bytes": TARGET_BYTES,
            "hard_bytes": HARD_BYTES,
        },
        "system": {
            "home_assistant": _pick(report.get("home_assistant") or {}, ("version", "time_zone", "components_count")),
            "supervisor": _pick(report.get("supervisor") or {}, ("version", "healthy", "supported")),
            "host": _pick(report.get("host") or {}, ("operating_system", "kernel")),
        },
        "inventory_summary": _pick(inventory, (
            "states", "unavailable_count", "unknown_count", "yaml_files_scanned",
            "yaml_bytes_scanned", "automations_detected", "blueprints_detected",
            "entity_references_detected",
        )),
        "diagnostic_summary": {
            **_pick(diagnostic, (
                "priority_counts", "actionable_count", "headline", "source",
                "plan_id_count", "controller_review_entity_count",
                "controller_review_pair_count",
            )),
            "top_actions": [
                _pick(item, ("id", "title", "severity", "domain", "confidence"))
                for item in (diagnostic.get("top_actions") or [])[:5]
            ],
        },
        "executive_summary": {
            **_pick(executive, (
                "health_score", "health_label", "root_cause_count",
                "actionable_root_cause_count", "detected_root_cause_count",
                "complexity_score", "complexity_label", "trend_state",
                "maintenance_debt_score", "flow_target_resolution_rate",
                "automation_coverage_ratio", "shared_actuator_count",
                "closed_loop_count", "critical_dependency_count",
                "contextual_health_score_preview", "score_v5_preview",
                "projected_after_top_3_fixes", "entity_lineage_confirmed_edges",
                "protocol_handoff_count", "resilience_recommendation_count",
                "branch_protocol_resolved_pair_count",
                "controller_review_entity_count", "controller_review_pair_count",
            )),
            "text": _text(executive.get("text"), 620 if level == 0 else 420),
            "top_priority_titles": (executive.get("top_priority_titles") or [])[:5],
        },
        "controller_review_summary": _trim(report.get("controller_review_summary") or {}, max_items=12, text_limit=200),
        "findings": [
            _compact_finding(item, level)
            for item in (report.get("findings") or [])[:24]
            if isinstance(item, dict)
        ],
        "action_plan": {
            "model": plan.get("model"),
            "total": plan.get("total", len(plan_items)),
            "counts": plan.get("counts") or {},
            "items": [_compact_action(item, level) for item in plan_items[:30]],
        },
        "non_plan_observations": [_compact_observation(item) for item in observations[:12]],
        "entity_health_summary": _health_summary(report, level),
        "registry_summary": _registry_actionable_summary(report, level),
        "flow_confidence": _pick(report.get("flow_confidence") or {}, (
            "model", "target_resolution_rate", "dynamic_target_resolution_rate",
            "static_control_edges", "dynamic_control_edges",
            "dynamic_confidence_bands", "literal_confirmed_promotions",
            "review_required_dynamic_edges", "review_required_ratio",
            "low_confidence_dynamic_edges", "low_confidence_ratio",
            "unresolved_dynamic_targets", "quality_status",
        )),
        "condition_semantics": _semantics_summary(report, level),
        "architecture_summary": _architecture_summary(report, level),
        "entity_lineage_summary": _pick(lineage, (
            "model", "edge_count", "confirmed_edge_count", "source_entity_count",
            "derived_entity_count", "known_entity_count", "unresolved_output_count",
            "parse_error_count", "max_depth_for_blast_radius",
        )),
        "resilience": _resilience_summary(report),
        "root_cause_summary": _pick(report.get("root_cause_summary") or {}, (
            "actionable_registry_incidents", "integration_incidents",
            "device_incidents", "cluster_incidents", "transient_observations",
            "noise_suppressed", "detected_registry_incidents",
            "registry_impacted_automation_count", "registry_lineage_incident_count",
            "registry_high_or_critical_incident_count",
        )),
        "temporal_analysis": _temporal_summary(report),
        **_quality_summary(report),
        "score_v5_preview": _score_preview(report, level),
        "report_schema": {
            "version": (report.get("report_schema") or {}).get("version"),
            "capabilities_count": len((report.get("report_schema") or {}).get("capabilities") or []),
        },
    }
    return result


def _minimal_fallback(report):
    result = _build(report, level=1)
    for finding in result.get("findings") or []:
        finding.pop("examples", None)
        finding.pop("recommendation", None)
        finding["summary"] = _text(finding.get("summary"), 180)
    for item in (result.get("action_plan") or {}).get("items") or []:
        item.pop("first_check", None)
    result["entity_health_summary"] = {
        key: _pick(value, (
            "total", "stateful_count", "ignored_stateless_count",
            "attention_count", "review_count",
        ))
        for key, value in (result.get("entity_health_summary") or {}).items()
    }
    result["architecture_summary"].pop("top_hotspots", None)
    result["architecture_summary"].pop("critical_dependencies", None)
    result["non_plan_observations"] = [
        _pick(item, ("id", "title", "priority", "severity", "source_type", "source_id"))
        for item in (result.get("non_plan_observations") or [])
    ]
    return result


def build_share_report(report):
    if not isinstance(report, dict):
        return None

    result = _build(report, level=0)
    detail_level = "standard"
    if _json_size(result) > TARGET_BYTES:
        result = _build(report, level=1)
        detail_level = "compact"
    if _json_size(result) > TARGET_BYTES:
        result = _minimal_fallback(report)
        detail_level = "minimal"

    full_size = _json_size(report)
    result["export_meta"] = {
        "type": MODEL,
        "intended_for": "assistant_or_support_analysis",
        "detail_level": detail_level,
        "target_bytes": TARGET_BYTES,
        "hard_bytes": HARD_BYTES,
        "full_report_bytes_estimate": full_size,
        "raw_states_included": False,
        "raw_yaml_included": False,
        "secret_values_included": False,
        "full_dependency_graph_included": False,
        "entity_ids_preserved": True,
        "source_finding_count": len(report.get("findings") or []),
        "exported_finding_count": len(result.get("findings") or []),
        "source_action_count": len((report.get("action_plan") or {}).get("items") or []),
        "exported_action_count": len((result.get("action_plan") or {}).get("items") or []),
    }
    result["export_meta"]["share_report_bytes_estimate"] = _json_size(result)

    if _json_size(result) > HARD_BYTES:
        for key in (
            "entity_health_summary", "architecture_summary", "non_plan_observations",
            "score_v5_preview",
        ):
            result.pop(key, None)
        result["export_meta"]["detail_level"] = "hard_bounded"
        result["export_meta"]["secondary_sections_omitted"] = True
        result["export_meta"]["share_report_bytes_estimate"] = _json_size(result)

    return result
