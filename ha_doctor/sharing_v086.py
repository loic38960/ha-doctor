"""HA Doctor 0.8.6 compact share-report builder.

The full diagnostic report remains available locally. This module creates a
bounded, non-anonymized diagnostic packet intended to be attached to an
assistant/support conversation without carrying the large repeated graph and
registry payloads from the full report.
"""
import json

VERSION = "0.8.6"
MODEL = "assistant_share_report_v1"

_FINDING_LIMIT = 30
_ACTION_LIMIT = 30
_OBSERVATION_LIMIT = 20
_REGISTRY_GROUP_LIMIT = 14
_HEALTH_GROUP_LIMIT = 12
_ARCH_ITEM_LIMIT = 12
_TEXT_LIMIT = 700

_HEAVY_LIST_KEYS = {
    "affected_entities",
    "entities",
    "references",
    "reads",
    "controls",
    "triggers_on",
    "automation_evidence",
    "impacted_automations",
    "high_risk_automations",
    "top_entities",
    "edges",
}


def _pick(source, keys):
    if not isinstance(source, dict):
        return {}
    return {key: source.get(key) for key in keys if key in source}


def _trim(value, max_items=6, depth=0):
    if depth > 6:
        return None
    if isinstance(value, str):
        return value if len(value) <= _TEXT_LIMIT else value[:_TEXT_LIMIT] + "…"
    if isinstance(value, list):
        return [_trim(item, max_items=max_items, depth=depth + 1) for item in value[:max_items]]
    if not isinstance(value, dict):
        return value

    result = {}
    for key, item in value.items():
        if key in _HEAVY_LIST_KEYS and isinstance(item, list):
            result[f"{key}_count"] = len(item)
            if item:
                result[f"{key}_examples"] = [
                    _trim(entry, max_items=4, depth=depth + 1)
                    for entry in item[:4]
                ]
            continue
        result[key] = _trim(item, max_items=max_items, depth=depth + 1)
    return result


def _compact_action(item):
    result = _pick(item, (
        "id", "title", "priority", "priority_label", "severity", "domain",
        "confidence", "confidence_label", "confidence_score", "diagnosis",
        "impact", "why_now", "first_check", "source_type", "source_id",
    ))
    temporal = item.get("temporal") or {}
    if temporal:
        result["temporal"] = _pick(temporal, (
            "status", "scope", "occurrences", "qualified_observations",
            "first_seen", "last_seen_before_current", "age_seconds",
            "persistence_factor", "model",
        ))
    impact = item.get("dependency_impact") or {}
    if impact:
        result["dependency_impact"] = _pick(impact, (
            "model", "level", "impacted_automation_count",
            "high_risk_automation_count", "critical_automation_count",
            "helper_only_automation_count", "weighted_impact_score",
            "score_multiplier", "lineage_used", "scoring_applied",
        ))
    evidence = item.get("evidence") or []
    if evidence:
        result["evidence"] = [
            _pick(entry, ("type", "label", "text"))
            for entry in evidence[:3]
            if isinstance(entry, dict)
        ]
    return result


def _compact_finding(item):
    result = _pick(item, (
        "rule_id", "title", "severity", "domain", "summary",
        "recommendation", "priority", "priority_label",
    ))
    examples = item.get("examples") or []
    if examples:
        result["examples"] = [_trim(example, max_items=4) for example in examples[:4]]
        result["example_count"] = len(examples)
    return result


def _compact_diagnostic(item):
    result = _pick(item, (
        "id", "title", "priority", "severity", "domain", "confidence",
        "confidence_score", "diagnosis", "impact", "source_type", "source_id",
    ))
    temporal = item.get("temporal") or {}
    if temporal:
        result["temporal"] = _pick(temporal, (
            "status", "scope", "occurrences", "qualified_observations",
            "first_seen", "persistence_factor",
        ))
    dependency = item.get("dependency_impact") or {}
    if dependency:
        result["dependency_impact"] = _pick(dependency, (
            "level", "impacted_automation_count", "high_risk_automation_count",
            "weighted_impact_score", "lineage_used",
        ))
    evidence = item.get("evidence") or []
    if evidence:
        result["evidence"] = [
            _pick(entry, ("type", "label", "text"))
            for entry in evidence[:3]
            if isinstance(entry, dict)
        ]
    return result


def _compact_health_group(item):
    return _pick(item, ("key", "label", "count", "examples"))


def _compact_registry_group(item):
    return _pick(item, (
        "integration", "name", "manufacturer", "model",
        "total", "core_total", "core_affected", "healthy",
        "unavailable", "unknown", "missing_state", "optional_affected",
        "affected_ratio", "status", "contextual_status", "context_factor",
        "status_note", "examples", "platforms", "transient_or_sleep_tolerant",
    ))


def _compact_architecture_item(item):
    if not isinstance(item, dict):
        return item
    return _trim(item, max_items=5)


def _json_size(value):
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except Exception:
        return 0


def build_share_report(report):
    if not isinstance(report, dict):
        return None

    result = _pick(report, (
        "product", "version", "generated_at", "scan_duration_seconds",
        "scores", "severity_counts",
    ))
    result["share_schema"] = {
        "version": "ha-doctor-share/1",
        "model": MODEL,
        "source_report_version": report.get("version"),
    }

    result["home_assistant"] = _pick(report.get("home_assistant") or {}, (
        "version", "time_zone", "components_count",
    ))
    result["supervisor"] = _pick(report.get("supervisor") or {}, (
        "version", "healthy", "supported",
    ))
    result["host"] = _pick(report.get("host") or {}, (
        "operating_system", "kernel",
    ))

    inventory = report.get("inventory") or {}
    result["inventory_summary"] = _pick(inventory, (
        "states", "unavailable_count", "unknown_count", "yaml_files_scanned",
        "yaml_bytes_scanned", "automations_detected", "blueprints_detected",
        "entity_references_detected",
    ))

    result["diagnostic_summary"] = _trim(report.get("diagnostic_summary") or {}, max_items=8)
    result["executive_summary"] = _trim(report.get("executive_summary") or {}, max_items=8)

    score_meta = report.get("score_meta") or {}
    result["score_meta"] = _pick(score_meta, (
        "model", "legacy_global", "previous_global", "penalty_total",
        "domain_penalties", "penalty_breakdown", "hardening_version",
        "condition_semantics_model", "call_graph_model", "resilience_model",
        "quality_gate_model", "flow_confidence_model", "score_v5_model",
        "architecture_model", "entity_lineage_model",
    ))

    findings = report.get("findings") or []
    result["findings"] = [_compact_finding(item) for item in findings[:_FINDING_LIMIT]]

    plan = report.get("action_plan") or {}
    plan_items = plan.get("items") or []
    result["action_plan"] = {
        "model": plan.get("model"),
        "total": plan.get("total", len(plan_items)),
        "counts": plan.get("counts") or {},
        "items": [_compact_action(item) for item in plan_items[:_ACTION_LIMIT]],
    }

    plan_ids = {
        str(item.get("id") or "")
        for item in plan_items
        if isinstance(item, dict) and item.get("id")
    }
    observations = [
        item for item in (report.get("diagnostic_explanations") or [])
        if isinstance(item, dict) and str(item.get("id") or "") not in plan_ids
    ]
    result["non_plan_observations"] = [
        _compact_diagnostic(item) for item in observations[:_OBSERVATION_LIMIT]
    ]

    health = report.get("entity_health") or {}
    result["entity_health_summary"] = {}
    for key in ("unavailable", "unknown"):
        section = health.get(key) or {}
        result["entity_health_summary"][key] = {
            **_pick(section, (
                "total", "stateful_count", "ignored_stateless_count",
                "likely_transient_count", "likely_optional_count",
                "attention_count", "review_count", "triage_note",
            )),
            "groups": [
                _compact_health_group(group)
                for group in (section.get("groups") or [])[:_HEALTH_GROUP_LIMIT]
            ],
        }

    registry = report.get("registry_analysis") or {}
    integrations = registry.get("integration_health") or {}
    devices = registry.get("device_health") or {}
    integration_groups = [
        item for item in (integrations.get("groups") or [])
        if item.get("status") in {"offline", "degraded", "watch"}
    ]
    device_groups = [
        item for item in (devices.get("groups") or [])
        if item.get("status") in {"offline", "degraded", "watch"}
    ]
    orphan = registry.get("orphan_analysis") or {}
    result["registry_summary"] = {
        "available": registry.get("available"),
        "entity_registry_count": registry.get("entity_registry_count"),
        "device_registry_count": registry.get("device_registry_count"),
        "integration_health": {
            **_pick(integrations, ("total", "affected", "offline", "problematic")),
            "groups": [
                _compact_registry_group(item)
                for item in integration_groups[:_REGISTRY_GROUP_LIMIT]
            ],
        },
        "device_health": {
            **_pick(devices, ("total", "affected", "offline", "problematic")),
            "groups": [
                _compact_registry_group(item)
                for item in device_groups[:_REGISTRY_GROUP_LIMIT]
            ],
        },
        "orphan_analysis": _pick(orphan, (
            "registry_only_count", "candidate_count", "high_confidence_count",
            "probable_orphan_count", "review_candidate_count",
        )),
    }

    result["flow_confidence"] = _trim(report.get("flow_confidence") or {}, max_items=8)

    semantics = report.get("condition_semantics") or {}
    result["condition_semantics"] = {
        **_pick(semantics, (
            "model", "automation_count_with_required_state_guards",
            "controller_pairs_analyzed", "proven_exclusive_pair_count",
            "coordinated_pair_count", "resolved_pair_count",
            "unproven_pair_count", "physical_unproven_pair_count",
            "helper_unproven_pair_count", "other_unproven_pair_count",
            "contradictory_deterministic_pair_count",
            "protocol_coordinated_pair_count",
            "branch_protocol_resolved_pair_count", "confidence", "note",
        )),
        "unproven_pairs": [
            _trim(item, max_items=5)
            for item in (semantics.get("unproven_pairs") or [])[:_ARCH_ITEM_LIMIT]
        ],
        "branch_protocol_resolved_pairs": [
            _trim(item, max_items=5)
            for item in (semantics.get("branch_protocol_resolved_pairs") or [])[:_ARCH_ITEM_LIMIT]
        ],
    }

    architecture = report.get("architecture_analysis") or {}
    result["architecture_summary"] = {
        **_pick(architecture, (
            "model", "complexity_score", "complexity_label", "automation_count",
            "entity_dependency_count", "entity_edge_count", "control_edge_count",
            "call_edge_count", "dynamic_target_resolution_rate",
            "target_resolution_rate", "unresolved_dynamic_target_count",
            "shared_actuator_count", "helper_hub_count", "trigger_hub_count",
            "call_hub_count", "critical_dependency_count", "closed_loop_count",
            "post_flow_recomputed", "flow_confidence_model",
            "condition_semantics_model", "protocol_coordinated_pair_count",
            "physical_unproven_controller_pair_count",
            "helper_unproven_controller_pair_count",
            "branch_protocol_resolved_pair_count",
        )),
        "top_hotspots": [
            _compact_architecture_item(item)
            for item in (architecture.get("top_hotspots") or [])[:_ARCH_ITEM_LIMIT]
        ],
        "critical_dependencies": [
            _compact_architecture_item(item)
            for item in (architecture.get("critical_dependencies") or [])[:8]
        ],
        "call_hubs": [
            _compact_architecture_item(item)
            for item in (architecture.get("call_hubs") or [])[:8]
        ],
        "closed_loops": [
            _compact_architecture_item(item)
            for item in (architecture.get("closed_loops") or [])[:8]
        ],
    }

    lineage = report.get("entity_lineage") or {}
    result["entity_lineage_summary"] = {
        **_pick(lineage, (
            "model", "edge_count", "confirmed_edge_count", "source_entity_count",
            "derived_entity_count", "known_entity_count", "unresolved_output_count",
            "parse_error_count", "max_depth_for_blast_radius", "interpretation",
        )),
        "unresolved_outputs": _trim(lineage.get("unresolved_outputs") or [], max_items=8),
        "parse_errors": _trim(lineage.get("parse_errors") or [], max_items=8),
    }

    resilience = report.get("resilience_analysis") or {}
    result["resilience_analysis"] = {
        **_pick(resilience, (
            "model", "critical_dependency_count", "external_spof_count",
            "helper_dependency_count", "review_count", "partial_count",
            "protected_count", "configuration_dependency_count",
            "not_applicable_count", "numeric_default_only_count",
            "unprotected_automation_count", "note",
        )),
        "items": [
            _pick(item, (
                "entity_id", "criticality", "automation_count",
                "explicit_guard_count", "numeric_default_only_count",
                "unprotected_count", "status", "counts_as_external_spof",
                "unprotected_automations",
            ))
            for item in (resilience.get("items") or [])[:10]
        ],
    }

    result["resilience_recommendations"] = _trim(
        report.get("resilience_recommendations") or {}, max_items=10
    )
    result["root_cause_summary"] = _trim(report.get("root_cause_summary") or {}, max_items=8)
    result["temporal_analysis"] = _trim(report.get("temporal_analysis") or {}, max_items=10)
    result["quality_gates"] = _trim(report.get("quality_gates") or {}, max_items=20)
    result["consistency_analysis"] = _trim(report.get("consistency_analysis") or {}, max_items=20)
    result["score_v5_preview"] = _trim(report.get("score_v5_preview") or {}, max_items=12)
    result["report_schema"] = _trim(report.get("report_schema") or {}, max_items=30)

    full_size = _json_size(report)
    result["export_meta"] = {
        "type": MODEL,
        "intended_for": "assistant_or_support_analysis",
        "non_anonymized": True,
        "entity_ids_preserved": True,
        "full_dependency_graph_included": False,
        "raw_states_included": False,
        "raw_yaml_included": False,
        "secret_values_included": False,
        "full_report_bytes_estimate": full_size,
        "source_finding_count": len(findings),
        "exported_finding_count": min(len(findings), _FINDING_LIMIT),
        "source_action_count": len(plan_items),
        "exported_action_count": min(len(plan_items), _ACTION_LIMIT),
        "source_non_plan_observation_count": len(observations),
        "exported_non_plan_observation_count": min(len(observations), _OBSERVATION_LIMIT),
        "note": (
            "Export compact pour partage privé avec un assistant/support. "
            "Le rapport complet reste disponible localement."
        ),
    }
    result["export_meta"]["share_report_bytes_estimate"] = _json_size(result)
    return result
