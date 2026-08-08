"""Privacy-oriented exports for HA Doctor 0.7."""


def _safe_quality(quality):
    gates = []
    for item in (quality or {}).get("gates") or []:
        gates.append({
            "key": item.get("key"),
            "status": item.get("status"),
        })
    return {
        "overall": (quality or {}).get("overall"),
        "counts": (quality or {}).get("counts"),
        "gates": gates,
    }


def build_anonymized_report(report):
    if not isinstance(report, dict):
        return None
    inventory = report.get("inventory") or {}
    plan = report.get("action_plan") or {}
    temporal = report.get("temporal_analysis") or {}
    regression = report.get("regression_analysis") or {}
    roots = report.get("root_cause_summary") or {}
    engine = report.get("diagnostic_engine") or {}
    architecture = report.get("architecture_analysis") or {}
    maintenance = report.get("maintenance_debt") or {}
    graph_meta = report.get("dependency_graph_meta") or {}
    findings = report.get("findings") or []

    safe_actions = []
    for item in plan.get("items") or []:
        row = {
            "priority": item.get("priority"),
            "severity": item.get("severity"),
            "domain": item.get("domain"),
            "confidence": item.get("confidence"),
            "source_type": item.get("source_type"),
            "temporal_status": (item.get("temporal") or {}).get("status"),
            "dependency_impact": (item.get("dependency_impact") or {}).get("level"),
            "critical_automation_count": (item.get("dependency_impact") or {}).get("critical_automation_count"),
            "helper_fanout_discounted": (item.get("dependency_impact") or {}).get("helper_fanout_discounted"),
        }
        if item.get("source_type") == "finding":
            row["rule_id"] = item.get("source_id")
        safe_actions.append(row)

    safe_findings = []
    for item in findings:
        safe_findings.append({
            "rule_id": item.get("rule_id"),
            "severity": item.get("severity"),
            "domain": item.get("domain"),
            "priority": item.get("priority"),
        })

    return {
        "product": report.get("product", "HA Doctor"),
        "version": report.get("version"),
        "generated_at": report.get("generated_at"),
        "scan_duration_seconds": report.get("scan_duration_seconds"),
        "report_schema": report.get("report_schema"),
        "scores": report.get("scores"),
        "score_meta": {
            "model": (report.get("score_meta") or {}).get("model"),
            "alpha": (report.get("score_meta") or {}).get("alpha"),
            "root_cause_scoring": (report.get("score_meta") or {}).get("root_cause_scoring"),
            "temporal_scoring": (report.get("score_meta") or {}).get("temporal_scoring"),
            "dependency_scoring": (report.get("score_meta") or {}).get("dependency_scoring"),
            "raw_entity_volume_scoring": (report.get("score_meta") or {}).get("raw_entity_volume_scoring"),
            "helper_fanout_discounted": (report.get("score_meta") or {}).get("helper_fanout_discounted"),
            "category_penalty_caps": (report.get("score_meta") or {}).get("category_penalty_caps"),
            "penalty_total": (report.get("score_meta") or {}).get("penalty_total"),
        },
        "inventory_summary": {
            "states": inventory.get("states"),
            "yaml_files_scanned": inventory.get("yaml_files_scanned"),
            "automations_detected": inventory.get("automations_detected"),
            "blueprints_detected": inventory.get("blueprints_detected"),
            "unavailable_count": inventory.get("unavailable_count"),
            "unknown_count": inventory.get("unknown_count"),
        },
        "diagnostic_engine": {
            "version": engine.get("version"),
            "mode": engine.get("mode"),
            "explanation_count": engine.get("explanation_count"),
            "registry_incident_count": engine.get("registry_incident_count"),
            "plan_noise_suppressed_count": engine.get("plan_noise_suppressed_count"),
            "architecture_analysis": engine.get("architecture_analysis"),
            "regression_analysis": engine.get("regression_analysis"),
            "external_ai_used": engine.get("external_ai_used"),
            "automatic_fix": engine.get("automatic_fix"),
            "read_only": engine.get("read_only"),
        },
        "action_plan": {
            "total": plan.get("total"),
            "counts": plan.get("counts"),
            "suppressed_noise_count": len(plan.get("suppressed_noise") or []),
            "items": safe_actions,
        },
        "root_cause_summary": roots,
        "temporal_summary": {
            "enabled": temporal.get("enabled"),
            "model": temporal.get("model"),
            "scan_count": temporal.get("scan_count"),
            "previous_score": temporal.get("previous_score"),
            "score_delta": temporal.get("score_delta"),
            "new_count": temporal.get("new_count"),
            "persistent_count": temporal.get("persistent_count"),
            "resolved_since_previous_count": temporal.get("resolved_since_previous_count"),
            "trend_state": temporal.get("trend_state"),
            "score_history": temporal.get("score_history"),
        },
        "regression_summary": {
            "state": regression.get("state"),
            "score_delta": regression.get("score_delta"),
            "new_diagnostic_count": regression.get("new_diagnostic_count"),
            "new_action_now_count": regression.get("new_action_now_count"),
            "resolved_count": regression.get("resolved_count"),
            "persistent_count": regression.get("persistent_count"),
            "requires_attention": regression.get("requires_attention"),
        },
        "architecture_summary": {
            "model": architecture.get("model"),
            "complexity_score": architecture.get("complexity_score"),
            "complexity_label": architecture.get("complexity_label"),
            "automation_count": architecture.get("automation_count"),
            "entity_dependency_count": architecture.get("entity_dependency_count"),
            "entity_edge_count": architecture.get("entity_edge_count"),
            "shared_actuator_count": architecture.get("shared_actuator_count"),
            "helper_hub_count": architecture.get("helper_hub_count"),
            "trigger_hub_count": architecture.get("trigger_hub_count"),
            "closed_loop_count": architecture.get("closed_loop_count"),
        },
        "dependency_graph_summary": {
            "model": graph_meta.get("model"),
            "automation_nodes": graph_meta.get("automation_nodes"),
            "service_references_removed": graph_meta.get("service_references_removed"),
            "entity_edges": graph_meta.get("entity_edges"),
            "trigger_edges": graph_meta.get("trigger_edges"),
            "control_edges": graph_meta.get("control_edges"),
        },
        "maintenance_debt": {
            "score": maintenance.get("score"),
            "label": maintenance.get("label"),
            "missing_reference_count": maintenance.get("missing_reference_count"),
            "probable_orphan_count": maintenance.get("probable_orphan_count"),
            "local_review_candidate_count": maintenance.get("local_review_candidate_count"),
            "archived_secret_hint_count": maintenance.get("archived_secret_hint_count"),
            "automation_coverage_ratio": maintenance.get("automation_coverage_ratio"),
            "automation_coverage_gap": maintenance.get("automation_coverage_gap"),
        },
        "quality_gates": _safe_quality(report.get("quality_gates") or {}),
        "findings": safe_findings,
        "privacy": {
            "raw_states_included": False,
            "secret_values_included": False,
            "entity_ids_included": False,
            "device_names_included": False,
            "integration_names_included": False,
            "automation_names_included": False,
            "file_paths_included": False,
        },
        "export_meta": {
            "type": "anonymized_diagnostic",
            "intended_for_sharing": True,
            "identifiers_removed": True,
            "technical_detail_level": "aggregate",
        },
    }
