"""HA Doctor 0.15 event-aware controller semantics.

V10 keeps V9 branch/numeric proofs and adds the missing temporal distinction
between a numeric_state *crossing event* and a continuously true state window.
It remains fully static: no Jinja execution and no runtime simulation.
"""

import semantics_v081 as sem_v1
import semantics_v082 as sem_v2
import semantics_v140 as base
from contracts_v150 import CONDITION_MODEL, POLICY_CONFLICT_MODEL


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _trigger_metadata(effective):
    result = {}
    for idx, trigger in enumerate(sem_v2._trigger_list(effective or {})):
        if not isinstance(trigger, dict):
            continue
        trigger_id = str(trigger.get("id") or f"trigger[{idx}]")
        platform = str(trigger.get("platform") or trigger.get("trigger") or "").lower()
        result[trigger_id] = {
            "platform": platform,
            "for": trigger.get("for"),
            "crossing_semantics": platform == "numeric_state",
        }
    return result


def _event_analysis(pair, by_alias):
    aliases = [str(x) for x in pair.get("automations") or []]
    target = str(pair.get("entity_id") or "")
    if len(aliases) != 2:
        return None
    records_a = by_alias.get(aliases[0]) or []
    records_b = by_alias.get(aliases[1]) or []
    if len(records_a) != 1 or len(records_b) != 1:
        return None

    effective_a = records_a[0].get("effective") or {}
    effective_b = records_b[0].get("effective") or {}
    meta_a = _trigger_metadata(effective_a)
    meta_b = _trigger_metadata(effective_b)
    paths_a = base._path_profiles(records_a[0], target)
    paths_b = base._path_profiles(records_b[0], target)

    conflicts = []
    for path_a in paths_a:
        for path_b in paths_b:
            if path_a.get("intent") == path_b.get("intent"):
                continue
            relation = base._pair_numeric_relation(path_a, path_b)
            if relation.get("disjoint"):
                continue
            overlaps = relation.get("overlaps") or []
            if not overlaps:
                continue
            trigger_a = str(path_a.get("trigger_id") or "")
            trigger_b = str(path_b.get("trigger_id") or "")
            ma = meta_a.get(trigger_a, {"platform": str(path_a.get("trigger_platform") or "").lower(), "for": None})
            mb = meta_b.get(trigger_b, {"platform": str(path_b.get("trigger_platform") or "").lower(), "for": None})
            numeric_a = ma.get("platform") == "numeric_state"
            numeric_b = mb.get("platform") == "numeric_state"
            if numeric_a and numeric_b:
                event_kind = "crossing_event_window"
            elif numeric_a or numeric_b:
                event_kind = "event_vs_policy_window"
            else:
                event_kind = "state_policy_window"
            conflicts.append({
                "intent_a": path_a.get("intent"), "intent_b": path_b.get("intent"),
                "trigger_a": trigger_a or None, "trigger_b": trigger_b or None,
                "trigger_platform_a": ma.get("platform"), "trigger_platform_b": mb.get("platform"),
                "trigger_for_a": ma.get("for"), "trigger_for_b": mb.get("for"),
                "event_kind": event_kind,
                "overlap_evidence": overlaps[:6],
                "branch_a": path_a.get("branch_path") or [], "branch_b": path_b.get("branch_path") or [],
                "retrigger_requires_boundary_recross": bool(numeric_a and numeric_b),
            })

    if not conflicts:
        return None
    kinds = sorted({str(x.get("event_kind")) for x in conflicts})
    crossing = [x for x in conflicts if x.get("event_kind") == "crossing_event_window"]
    return {
        "model": POLICY_CONFLICT_MODEL,
        "status": "event_window_policy_overlap",
        "conflict_path_pair_count": len(conflicts),
        "crossing_event_conflict_count": len(crossing),
        "event_kinds": kinds,
        "conflicts": conflicts[:8],
        "simultaneous_execution_proven": False,
        "continuous_conflict_proven": False,
        "templates_executed": False,
        "numeric_state_crossing_semantics_applied": bool(crossing),
        "interpretation": (
            "Une fenêtre de politique opposée existe statiquement. Un trigger numeric_state se déclenche à l'entrée de sa plage ; "
            "la présence d'un overlap ne prouve donc ni exécution simultanée ni boucle continue."
        ),
    }


def refine_condition_semantics_v10(report):
    current = base.refine_condition_semantics_v9(report)
    by_alias, parse_errors = sem_v1.effective_automation_map(report)
    remaining = []
    event_overlap_count = 0
    crossing_overlap_count = 0
    for raw in current.get("unproven_pairs") or []:
        if not isinstance(raw, dict):
            remaining.append(raw)
            continue
        enriched = dict(raw)
        v9 = raw.get("v9_policy_analysis") or {}
        if v9.get("status") == "policy_overlap" and str(raw.get("target_kind") or "") == "actuator":
            event = _event_analysis(raw, by_alias)
            if event:
                enriched["v10_event_analysis"] = event
                event_overlap_count += 1
                if event.get("crossing_event_conflict_count", 0):
                    crossing_overlap_count += 1
                enriched["evidence_level"] = "probable"
                enriched["review_priority"] = "high"
        remaining.append(enriched)

    result = {
        **current,
        "model": CONDITION_MODEL,
        "unproven_pairs": remaining,
        "event_window_policy_overlap_pair_count": event_overlap_count,
        "crossing_event_policy_overlap_pair_count": crossing_overlap_count,
        "v10_parse_error_count": len(parse_errors or []),
        "v10_policy": "event_aware_static_policy_overlap_without_runtime_claims",
        "templates_executed": False,
    }
    report["condition_semantics"] = result
    return result
