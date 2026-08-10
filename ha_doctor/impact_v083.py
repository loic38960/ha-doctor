"""HA Doctor 0.8.3 registry-to-automation blast radius correlation."""
from collections import defaultdict

import temporal_v060 as temporal_base

VERSION = "0.8.3"
MODEL = "registry_blast_radius_v3"


def _risk_map(report):
    result = {}
    for item in (report.get("architecture_analysis") or {}).get("automation_risk_profiles") or []:
        alias = str(item.get("automation") or "")
        if alias:
            result[alias] = float(item.get("risk_index", 0) or 0)
    return result


def _registry_entities(report, explanation):
    """Return the full compact affected-entity index for a registry incident."""
    registry = report.get("registry_analysis") or {}
    source_type = str(explanation.get("source_type") or "")
    source_id = str(explanation.get("source_id") or "")
    entities = set()

    if source_type == "registry_integration":
        for group in ((registry.get("integration_health") or {}).get("groups") or []):
            if str(group.get("integration") or "") == source_id:
                entities.update(str(x) for x in group.get("affected_entities") or [] if x)
                entities.update(str(x) for x in group.get("examples") or [] if x)
                break
    elif source_type == "registry_device":
        for group in ((registry.get("device_health") or {}).get("groups") or []):
            if str(group.get("name") or "") == source_id:
                entities.update(str(x) for x in group.get("affected_entities") or [] if x)
                entities.update(str(x) for x in group.get("examples") or [] if x)
                break
    elif source_type == "registry_cluster":
        for group in ((registry.get("device_health") or {}).get("groups") or []):
            platforms = {str(x) for x in group.get("platforms") or []}
            if source_id in platforms and str(group.get("status") or "") == "offline":
                entities.update(str(x) for x in group.get("affected_entities") or [] if x)
                entities.update(str(x) for x in group.get("examples") or [] if x)

    # Backward compatibility with old reports/fixtures that do not contain the
    # compact index yet.
    if not entities:
        try:
            entities.update(temporal_base._explanation_entities(report, explanation))
        except Exception:
            pass
    return sorted(entities)


def _impact_for_entities(report, entities):
    entities = set(entities or [])
    graph = report.get("dependency_graph") or []
    risks = _risk_map(report)
    impacted = set()
    critical = set()
    trigger_hits = control_hits = read_hits = call_hits = transitive_hits = 0
    entity_stats = defaultdict(lambda: {
        "trigger_hits": 0, "control_hits": 0, "read_hits": 0,
        "call_hits": 0, "transitive_hits": 0, "automations": set(),
    })

    for node in graph:
        alias = str(node.get("automation") or "Automatisation")
        triggers = set(node.get("triggers_on") or [])
        controls = set(node.get("controls") or [])
        reads = set(node.get("reads") or [])
        calls = set(node.get("calls") or [])
        refs = set(node.get("references") or [])
        transitive_controls = set(node.get("transitive_controls") or [])
        transitive_calls = set(node.get("transitive_calls") or [])

        touched = entities & (triggers | controls | reads | calls | refs | transitive_controls | transitive_calls)
        if not touched:
            continue
        impacted.add(alias)
        if risks.get(alias, 0) >= 18:
            critical.add(alias)

        for entity_id in touched:
            stat = entity_stats[entity_id]
            stat["automations"].add(alias)
            if entity_id in triggers:
                trigger_hits += 1
                stat["trigger_hits"] += 1
            if entity_id in controls:
                control_hits += 1
                stat["control_hits"] += 1
            if entity_id in reads:
                read_hits += 1
                stat["read_hits"] += 1
            if entity_id in calls:
                call_hits += 1
                stat["call_hits"] += 1
            if entity_id in transitive_controls or entity_id in transitive_calls:
                transitive_hits += 1
                stat["transitive_hits"] += 1

    weighted = (
        trigger_hits * 3.2
        + control_hits * 3.8
        + read_hits * 1.25
        + call_hits * 2.5
        + transitive_hits * 1.6
        + len(critical) * 2.0
    )
    count = len(impacted)
    if len(critical) >= 3 or weighted >= 28:
        level, multiplier = "critical", 1.18
    elif len(critical) or weighted >= 14 or count >= 5:
        level, multiplier = "high", 1.12
    elif weighted >= 5 or count >= 2:
        level, multiplier = "medium", 1.06
    elif count:
        level, multiplier = "low", 1.02
    else:
        level, multiplier = "none", 1.0

    top_entities = []
    for entity_id, stat in entity_stats.items():
        score = (
            stat["trigger_hits"] * 3.2 + stat["control_hits"] * 3.8
            + stat["read_hits"] * 1.25 + stat["call_hits"] * 2.5
            + stat["transitive_hits"] * 1.6
        )
        top_entities.append({
            "entity_id": entity_id,
            "automation_count": len(stat["automations"]),
            "trigger_hits": stat["trigger_hits"],
            "control_hits": stat["control_hits"],
            "read_hits": stat["read_hits"],
            "call_hits": stat["call_hits"],
            "transitive_hits": stat["transitive_hits"],
            "weight": round(score, 2),
        })
    top_entities.sort(key=lambda item: (-item["weight"], item["entity_id"]))

    return {
        "model": MODEL,
        "level": level,
        "impacted_automation_count": count,
        "high_risk_automation_count": len(critical),
        "impacted_automations": sorted(impacted)[:20],
        "high_risk_automations": sorted(critical)[:12],
        "trigger_dependency_count": trigger_hits,
        "control_dependency_count": control_hits,
        "read_dependency_count": read_hits,
        "call_dependency_count": call_hits,
        "transitive_dependency_count": transitive_hits,
        "weighted_impact_score": round(weighted, 2),
        "score_multiplier": multiplier,
        "top_entities": top_entities[:8],
        "entity_match_count": len(entities),
        "registry_correlation": True,
    }


def apply_registry_blast_radius_v3(report):
    explanations = report.get("diagnostic_explanations") or []
    by_id = {}
    registry_impacted = set()
    levels = defaultdict(int)

    for item in explanations:
        if not str(item.get("source_type") or "").startswith("registry_"):
            continue
        entities = _registry_entities(report, item)
        impact = _impact_for_entities(report, entities)
        item["dependency_impact"] = impact
        diagnostic_id = str(item.get("id") or "")
        if diagnostic_id:
            by_id[diagnostic_id] = impact
        registry_impacted.update(impact.get("impacted_automations") or [])
        levels[impact["level"]] += 1

    for section_name in ("action_plan", "recommendation_queue"):
        section = report.get(section_name) or {}
        for item in section.get("items") or []:
            diagnostic_id = str(item.get("id") or "")
            if diagnostic_id in by_id:
                item["dependency_impact"] = dict(by_id[diagnostic_id])

    root = report.setdefault("root_cause_summary", {})
    root.update({
        "registry_blast_radius_model": MODEL,
        "registry_impacted_automation_count": len(registry_impacted),
        "registry_blast_radius_levels": dict(levels),
        "registry_high_or_critical_incident_count": levels.get("high", 0) + levels.get("critical", 0),
    })
    report.setdefault("diagnostic_engine", {})["registry_blast_radius_v3"] = True
    return root
