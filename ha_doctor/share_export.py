"""Privacy-oriented exports for HA Doctor 0.6."""


def build_anonymized_report(report):
    if not isinstance(report, dict):
        return None
    inventory = report.get("inventory") or {}
    plan = report.get("action_plan") or {}
    temporal = report.get("temporal_analysis") or {}
    roots = report.get("root_cause_summary") or {}
    engine = report.get("diagnostic_engine") or {}
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
        "scores": report.get("scores"),
        "score_meta": {
            "model": (report.get("score_meta") or {}).get("model"),
            "alpha": (report.get("score_meta") or {}).get("alpha"),
            "root_cause_scoring": (report.get("score_meta") or {}).get("root_cause_scoring"),
            "temporal_scoring": (report.get("score_meta") or {}).get("temporal_scoring"),
            "dependency_scoring": (report.get("score_meta") or {}).get("dependency_scoring"),
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
        },
        "action_plan": {
            "total": plan.get("total"),
            "counts": plan.get("counts"),
            "items": safe_actions,
        },
        "root_cause_summary": roots,
        "temporal_summary": {
            "enabled": temporal.get("enabled"),
            "scan_count": temporal.get("scan_count"),
            "previous_score": temporal.get("previous_score"),
            "score_delta": temporal.get("score_delta"),
            "new_count": temporal.get("new_count"),
            "persistent_count": temporal.get("persistent_count"),
            "resolved_since_previous_count": temporal.get("resolved_since_previous_count"),
            "score_history": temporal.get("score_history"),
        },
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
