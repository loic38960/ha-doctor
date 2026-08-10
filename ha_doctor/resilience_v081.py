"""HA Doctor 0.8.1 static resilience / single-point-of-failure review."""
from semantics_v081 import effective_automation_map, required_state_guards

VERSION = "0.8.1"


def _has_fallback(effective, entity_id):
    text = repr(effective)
    guarded = entity_id in required_state_guards(effective.get("conditions", effective.get("condition", [])))
    explicit = entity_id in text and any(token in text for token in ("unavailable", "unknown", "has_value", "is_number"))
    numeric_default = entity_id in text and ("| float(" in text or "|float(" in text)
    return guarded or explicit or numeric_default


def build_resilience_analysis(report, states=None):
    critical = (report.get("architecture_analysis") or {}).get("critical_dependencies") or []
    by_alias, _ = effective_automation_map(report)
    graph = report.get("dependency_graph") or []
    items = []
    for dep in critical:
        entity_id = str(dep.get("entity_id") or "")
        users, protected = [], 0
        for node in graph:
            refs = set(node.get("references") or []) | set(node.get("triggers_on") or []) | set(node.get("reads") or [])
            if entity_id not in refs:
                continue
            alias = str(node.get("automation") or "")
            users.append(alias)
            records = by_alias.get(alias) or []
            if len(records) == 1 and _has_fallback(records[0]["effective"], entity_id):
                protected += 1
        ratio = protected / len(users) if users else 1.0
        status = "protected" if ratio >= 0.75 else ("partial" if ratio >= 0.25 else "review")
        items.append({
            "entity_id": entity_id,
            "criticality": dep.get("criticality"),
            "automation_count": len(users),
            "fallback_detected_count": protected,
            "fallback_coverage_ratio": round(ratio, 3),
            "status": status,
            "automations": users[:15],
        })
    result = {
        "model": "resilience_spof_v1",
        "critical_dependency_count": len(items),
        "review_count": sum(1 for x in items if x["status"] == "review"),
        "partial_count": sum(1 for x in items if x["status"] == "partial"),
        "protected_count": sum(1 for x in items if x["status"] == "protected"),
        "items": items[:20],
        "raw_yaml_persisted": False,
    }
    report["resilience_analysis"] = result
    return result
