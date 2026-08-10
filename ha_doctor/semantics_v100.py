"""Explainable unresolved controller semantics for HA Doctor 0.10.

V7 deliberately does not turn uncertain overlaps into PASS. It enriches the V6
result with deterministic intent and numeric-window evidence so the last real
controller conflicts are explainable instead of merely counted.
"""

import intelligence_v080 as architecture_base
import semantics_v081 as sem_v1
import semantics_v085 as branch
import semantics_v088 as base
from contracts_v100 import CONDITION_MODEL


def _number(value):
    try:
        return float(value)
    except Exception:
        return None


def _numeric_constraints(value, source="condition"):
    """Collect only literal numeric_state ranges. No template execution."""
    result = []
    if isinstance(value, list):
        for item in value:
            result.extend(_numeric_constraints(item, source=source))
        return result
    if not isinstance(value, dict):
        return result

    kind = str(value.get("condition") or value.get("platform") or value.get("trigger") or "").lower()
    if kind == "numeric_state":
        entities = branch.sem_v2._entity_ids(value.get("entity_id"))
        above = _number(value.get("above"))
        below = _number(value.get("below"))
        if entities and (above is not None or below is not None):
            for entity in entities:
                result.append({
                    "entity_id": str(entity),
                    "above": above,
                    "below": below,
                    "source": source,
                    "trigger_id": value.get("id") if source == "trigger" else None,
                })

    for key, child in value.items():
        if key in {"above", "below", "entity_id"}:
            continue
        if isinstance(child, (dict, list)):
            result.extend(_numeric_constraints(child, source=source))
    return result


def _intent_profile(record, target):
    effective = record.get("effective") or {}
    paths = branch._extract_paths(effective, target)
    intents = sorted({str(item.get("intent")) for item in paths if item.get("intent")})
    return {
        "intents": intents,
        "path_count": len(paths),
        "numeric_triggers": _numeric_constraints(effective.get("triggers", effective.get("trigger", [])), source="trigger"),
        "numeric_conditions": _numeric_constraints(effective.get("conditions", effective.get("condition", [])), source="condition"),
    }


def _ranges_overlap(a, b):
    if a.get("entity_id") != b.get("entity_id"):
        return None
    low_values = [x for x in (a.get("above"), b.get("above")) if x is not None]
    low = max(low_values) if low_values else None
    high_values = [x for x in (a.get("below"), b.get("below")) if x is not None]
    high = min(high_values) if high_values else None
    if low is not None and high is not None and low >= high:
        return {"overlap": False, "entity_id": a.get("entity_id"), "reason": "disjoint_literal_numeric_ranges"}
    return {
        "overlap": True,
        "entity_id": a.get("entity_id"),
        "above": low,
        "below": high,
        "reason": "literal_numeric_ranges_can_overlap",
    }


def _overlap_candidates(profile_a, profile_b):
    values_a = list(profile_a.get("numeric_triggers") or []) + list(profile_a.get("numeric_conditions") or [])
    values_b = list(profile_b.get("numeric_triggers") or []) + list(profile_b.get("numeric_conditions") or [])
    results = []
    seen = set()
    for a in values_a:
        for b in values_b:
            evidence = _ranges_overlap(a, b)
            if not evidence:
                continue
            key = (evidence.get("entity_id"), evidence.get("above"), evidence.get("below"), evidence.get("overlap"))
            if key in seen:
                continue
            seen.add(key)
            results.append(evidence)
    return results[:12]


def _annotate_pair(pair, by_alias):
    target = str(pair.get("entity_id") or "")
    aliases = [str(x) for x in pair.get("automations") or []]
    if len(aliases) != 2:
        return pair
    records_a = by_alias.get(aliases[0]) or []
    records_b = by_alias.get(aliases[1]) or []
    if len(records_a) != 1 or len(records_b) != 1:
        return {**pair, "v7_evidence": {"status": "insufficient_static_identity"}}

    profile_a = _intent_profile(records_a[0], target)
    profile_b = _intent_profile(records_b[0], target)
    intents_a = set(profile_a.get("intents") or [])
    intents_b = set(profile_b.get("intents") or [])
    opposing = bool(intents_a and intents_b and any(a != b for a in intents_a for b in intents_b))
    candidates = _overlap_candidates(profile_a, profile_b)
    overlaps = [item for item in candidates if item.get("overlap")]
    disjoint = [item for item in candidates if not item.get("overlap")]

    reason = "opposing_commands_require_review" if opposing else "same_direction_commands_not_proven_exclusive"
    if opposing and overlaps:
        reason = "opposing_commands_with_literal_numeric_overlap_candidate"
    evidence = {
        "model": CONDITION_MODEL,
        "status": "review",
        "reason": reason,
        "evidence_level": "hypothesis",
        "automation_a": {"alias": aliases[0], **profile_a},
        "automation_b": {"alias": aliases[1], **profile_b},
        "opposing_deterministic_intents": opposing,
        "numeric_overlap_candidates": overlaps[:6],
        "numeric_disjoint_evidence": disjoint[:6],
        "templates_executed": False,
        "note": "Une fenêtre numérique commune est un indice de chevauchement, pas une preuve d'exécution simultanée.",
    }
    return {**pair, "v7_evidence": evidence}


def refine_condition_semantics_v7(report):
    current = base.refine_condition_semantics_v6(report)
    by_alias, parse_errors = sem_v1.effective_automation_map(report)
    enriched = []
    overlap_pair_count = 0
    for pair in current.get("unproven_pairs") or []:
        if not isinstance(pair, dict):
            continue
        target = str(pair.get("entity_id") or "")
        if architecture_base._kind(target) == "actuator":
            pair = _annotate_pair(pair, by_alias)
            if ((pair.get("v7_evidence") or {}).get("numeric_overlap_candidates") or []):
                overlap_pair_count += 1
        enriched.append(pair)

    result = {
        **current,
        "model": CONDITION_MODEL,
        "unproven_pairs": enriched,
        "numeric_overlap_candidate_pair_count": overlap_pair_count,
        "v7_explainable_unproven_pair_count": sum(1 for item in enriched if item.get("v7_evidence")),
        "v7_parse_error_count": len(parse_errors or []),
        "v7_policy": "explain_overlap_without_false_resolution",
    }
    report["condition_semantics"] = result
    return result
