"""HA Doctor 0.8.2 static resilience calibration.

0.8.1 considered any numeric default such as ``| float(0)`` a fallback and
marked a critical dependency protected from 75% coverage. V2 distinguishes
explicit invalid-state handling from a weak numeric default and requires every
consumer to have strong protection before declaring a dependency protected.
"""

import re

from semantics_v081 import effective_automation_map

VERSION = "0.8.2"

_INVALID_TOKENS = ("unavailable", "unknown", "has_value", "is_number")


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def classify_fallback(effective, entity_id):
    """Classify static handling of an unavailable/invalid dependency.

    Returns one of:
    - explicit_guard: strong evidence that invalid states are checked;
    - numeric_default: weak evidence, e.g. float(0), which can be unsafe;
    - none: no static fallback evidence found.
    """
    escaped = re.escape(entity_id)
    state_ref = re.compile(rf"states\(\s*['\"]{escaped}['\"]\s*\)", re.IGNORECASE)
    numeric_default_re = re.compile(
        rf"states\(\s*['\"]{escaped}['\"]\s*\).*?\|\s*(?:float|int)\s*\(",
        re.IGNORECASE | re.DOTALL,
    )

    explicit = []
    defaults = []
    for text in _strings(effective):
        if entity_id not in text and not state_ref.search(text):
            continue
        lowered = text.lower()
        if any(token in lowered for token in _INVALID_TOKENS):
            explicit.append(text[:240])
        if numeric_default_re.search(text):
            defaults.append(text[:240])

    if explicit:
        return {
            "level": "strong",
            "kind": "explicit_guard",
            "evidence_count": len(explicit),
            "note": "Un contrôle explicite de valeur invalide est visible statiquement.",
        }
    if defaults:
        return {
            "level": "weak",
            "kind": "numeric_default",
            "evidence_count": len(defaults),
            "note": "Une valeur numérique par défaut existe, sans preuve qu'elle soit sûre métier.",
        }
    return {
        "level": "none",
        "kind": "none",
        "evidence_count": 0,
        "note": "Aucun fallback statique explicite détecté.",
    }


def build_resilience_analysis_v2(report):
    critical = (report.get("architecture_analysis") or {}).get("critical_dependencies") or []
    by_alias, _ = effective_automation_map(report)
    graph = report.get("dependency_graph") or []
    items = []

    for dep in critical:
        entity_id = str(dep.get("entity_id") or "")
        users = []
        strong = weak = unprotected = 0
        automation_evidence = []

        for node in graph:
            refs = (
                set(node.get("references") or [])
                | set(node.get("triggers_on") or [])
                | set(node.get("reads") or [])
            )
            if entity_id not in refs:
                continue

            alias = str(node.get("automation") or "")
            users.append(alias)
            records = by_alias.get(alias) or []
            classification = {"level": "none", "kind": "not_uniquely_resolved", "evidence_count": 0}
            if len(records) == 1:
                classification = classify_fallback(records[0].get("effective") or {}, entity_id)

            if classification["level"] == "strong":
                strong += 1
            elif classification["level"] == "weak":
                weak += 1
            else:
                unprotected += 1

            automation_evidence.append({
                "automation": alias,
                "protection": classification["level"],
                "evidence_kind": classification["kind"],
            })

        total = len(users)
        strong_ratio = strong / total if total else 1.0
        handled_ratio = (strong + weak) / total if total else 1.0

        if total == 0:
            status = "not_applicable"
        elif strong == total:
            status = "protected"
        elif strong or weak:
            status = "partial"
        else:
            status = "review"

        items.append({
            "entity_id": entity_id,
            "criticality": dep.get("criticality"),
            "automation_count": total,
            "explicit_guard_count": strong,
            "numeric_default_only_count": weak,
            "unprotected_count": unprotected,
            "strong_protection_ratio": round(strong_ratio, 3),
            "handled_or_defaulted_ratio": round(handled_ratio, 3),
            "status": status,
            "automations": users[:15],
            "automation_evidence": automation_evidence[:20],
            "interpretation": (
                "protected exige une protection explicite pour tous les consommateurs ; "
                "un simple float(0)/int(0) reste une protection faible à valider."
            ),
        })

    result = {
        "model": "resilience_spof_v2",
        "critical_dependency_count": len(items),
        "review_count": sum(1 for item in items if item["status"] == "review"),
        "partial_count": sum(1 for item in items if item["status"] == "partial"),
        "protected_count": sum(1 for item in items if item["status"] == "protected"),
        "not_applicable_count": sum(1 for item in items if item["status"] == "not_applicable"),
        "numeric_default_only_count": sum(item["numeric_default_only_count"] for item in items),
        "unprotected_automation_count": sum(item["unprotected_count"] for item in items),
        "items": items[:20],
        "raw_yaml_persisted": False,
        "note": (
            "Une valeur par défaut numérique n'est plus assimilée à un fallback sûr. "
            "Le statut protected exige 100 % de protections explicites."
        ),
    }
    report["resilience_analysis"] = result
    return result
