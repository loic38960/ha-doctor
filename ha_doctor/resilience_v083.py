"""HA Doctor 0.8.3 resilience calibration.

V3 treats exact state gates as fail-safe guards and separates state/configuration
helpers from real external single points of failure.
"""
import re

import intelligence_v080 as architecture_base
import resilience_v082 as base
from semantics_v081 import effective_automation_map, flow

VERSION = "0.8.3"
MODEL = "resilience_spof_v3"


def _structured_guard(value, entity_id):
    if isinstance(value, list):
        return any(_structured_guard(item, entity_id) for item in value)
    if not isinstance(value, dict):
        return False

    kind = str(value.get("condition") or "").lower()
    if kind == "state":
        entities = set(flow._entity_ids(value.get("entity_id")))
        states = value.get("state")
        if not isinstance(states, list):
            states = [states] if states is not None else []
        normalized = {str(x).lower() for x in states}
        if entity_id in entities and normalized and not normalized.intersection({"unknown", "unavailable"}):
            return True

    for child in value.values():
        if isinstance(child, (dict, list)) and _structured_guard(child, entity_id):
            return True
    return False


def _exact_state_trigger_guard(effective, entity_id):
    triggers = effective.get("triggers", effective.get("trigger", [])) if isinstance(effective, dict) else []
    if not isinstance(triggers, list):
        triggers = [triggers] if triggers else []
    for trigger in triggers:
        if not isinstance(trigger, dict):
            continue
        platform = str(trigger.get("platform") or trigger.get("trigger") or "").lower()
        if platform != "state":
            continue
        entities = set(flow._entity_ids(trigger.get("entity_id")))
        to_value = trigger.get("to")
        if entity_id in entities and isinstance(to_value, (str, int, float, bool)):
            if str(to_value).lower() not in {"unknown", "unavailable"}:
                return True
    return False


def classify_fallback_v3(effective, entity_id):
    previous = base.classify_fallback(effective, entity_id)
    if previous.get("level") == "strong":
        return previous
    if _structured_guard(effective, entity_id):
        return {
            "level": "strong",
            "kind": "structured_state_guard",
            "evidence_count": 1,
            "note": "Une condition state exacte empêche l'action quand la dépendance est invalide.",
        }
    if _exact_state_trigger_guard(effective, entity_id):
        return {
            "level": "strong",
            "kind": "exact_state_trigger_gate",
            "evidence_count": 1,
            "note": "Le trigger exact ne se déclenche pas sur unknown/unavailable.",
        }
    return previous


def build_resilience_analysis_v3(report):
    critical = (report.get("architecture_analysis") or {}).get("critical_dependencies") or []
    by_alias, _ = effective_automation_map(report)
    graph = report.get("dependency_graph") or []
    items = []

    for dep in critical:
        entity_id = str(dep.get("entity_id") or "")
        kind = architecture_base._kind(entity_id)
        users = []
        strong = weak = unprotected = 0
        evidence = []

        for node in graph:
            refs = set(node.get("references") or []) | set(node.get("triggers_on") or []) | set(node.get("reads") or [])
            if entity_id not in refs:
                continue
            alias = str(node.get("automation") or "")
            users.append(alias)
            records = by_alias.get(alias) or []
            classification = {"level": "none", "kind": "not_uniquely_resolved"}
            if len(records) == 1:
                classification = classify_fallback_v3(records[0].get("effective") or {}, entity_id)
            if classification.get("level") == "strong":
                strong += 1
            elif classification.get("level") == "weak":
                weak += 1
            else:
                unprotected += 1
            evidence.append({
                "automation": alias,
                "protection": classification.get("level", "none"),
                "evidence_kind": classification.get("kind", "none"),
            })

        total = len(users)
        if kind == "helper":
            status = "configuration_dependency"
        elif total == 0:
            status = "not_applicable"
        elif strong == total:
            status = "protected"
        elif strong or weak:
            status = "partial"
        else:
            status = "review"

        items.append({
            "entity_id": entity_id,
            "dependency_kind": kind,
            "criticality": dep.get("criticality"),
            "automation_count": total,
            "explicit_guard_count": strong,
            "numeric_default_only_count": weak,
            "unprotected_count": unprotected,
            "strong_protection_ratio": round(strong / total, 3) if total else 1.0,
            "handled_or_defaulted_ratio": round((strong + weak) / total, 3) if total else 1.0,
            "status": status,
            "automations": users[:20],
            "automation_evidence": evidence[:30],
            "counts_as_external_spof": kind == "sensor",
            "interpretation": (
                "Les helpers structurent l'état métier mais ne sont pas assimilés à une panne "
                "externe. Les capteurs externes restent évalués sur leurs gardes explicites."
            ),
        })

    result = {
        "model": MODEL,
        "critical_dependency_count": len(items),
        "external_spof_count": sum(1 for item in items if item["counts_as_external_spof"]),
        "helper_dependency_count": sum(1 for item in items if item["dependency_kind"] == "helper"),
        "review_count": sum(1 for item in items if item["status"] == "review"),
        "partial_count": sum(1 for item in items if item["status"] == "partial"),
        "protected_count": sum(1 for item in items if item["status"] == "protected"),
        "configuration_dependency_count": sum(1 for item in items if item["status"] == "configuration_dependency"),
        "not_applicable_count": sum(1 for item in items if item["status"] == "not_applicable"),
        "numeric_default_only_count": sum(item["numeric_default_only_count"] for item in items),
        "unprotected_automation_count": sum(
            item["unprotected_count"] for item in items if item["counts_as_external_spof"]
        ),
        "items": items[:30],
        "raw_yaml_persisted": False,
        "note": (
            "V3 ajoute les state gates exacts et évite de présenter un helper interne comme "
            "un SPOF matériel/réseau."
        ),
    }
    report["resilience_analysis"] = result
    return result
