"""HA Doctor 0.14 controller semantics.

V9 keeps every proof from V8 and adds branch/trigger-aware numeric policy
analysis. It never executes Jinja. Opposing command paths are compared only
with literal numeric_state constraints tied to the branch and trigger that can
reach that command.

A pair can be resolved when every opposing path is numerically disjoint. If a
shared state window remains, HA Doctor reports a policy overlap without
claiming simultaneous runtime execution.
"""

import intelligence_v080 as architecture_base
import semantics_v081 as sem_v1
import semantics_v082 as sem_v2
import semantics_v085 as branch
import semantics_v088 as sem_v6
import semantics_v130 as base
from contracts_v140 import CONDITION_MODEL, POLICY_CONFLICT_MODEL


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _number(value):
    try:
        return float(value)
    except Exception:
        return None


def _entity_ids(value):
    return {str(x) for x in sem_v2._entity_ids(value)}


def _numeric_constraints(value):
    result = []
    if isinstance(value, list):
        for item in value:
            result.extend(_numeric_constraints(item))
        return result
    if not isinstance(value, dict):
        return result
    kind = str(value.get("condition") or value.get("platform") or value.get("trigger") or "").lower()
    if kind == "numeric_state":
        above = _number(value.get("above")); below = _number(value.get("below"))
        if above is not None or below is not None:
            for entity in _entity_ids(value.get("entity_id")):
                result.append({"entity_id": entity, "above": above, "below": below})
    for key, child in value.items():
        if key in {"above", "below", "entity_id"}:
            continue
        if isinstance(child, (dict, list)):
            result.extend(_numeric_constraints(child))
    return result


def _trigger_condition_ids(value):
    ids = set()
    if isinstance(value, list):
        for item in value:
            ids |= _trigger_condition_ids(item)
        return ids
    if not isinstance(value, dict):
        return ids
    if str(value.get("condition") or "").lower() == "trigger":
        raw = value.get("id")
        for item in _as_list(raw):
            if item is not None:
                ids.add(str(item))
    for child in value.values():
        if isinstance(child, (dict, list)):
            ids |= _trigger_condition_ids(child)
    return ids


def _trigger_variants(effective):
    variants = []
    triggers = sem_v2._trigger_list(effective)
    for idx, trigger in enumerate(triggers):
        if not isinstance(trigger, dict):
            continue
        trigger_id = str(trigger.get("id") or f"trigger[{idx}]")
        variants.append({
            "id": trigger_id,
            "numeric": _numeric_constraints(trigger),
            "platform": str(trigger.get("platform") or trigger.get("trigger") or ""),
        })
    return variants


def _service_intent(action, target):
    service, targets = branch._service_and_targets(action)
    if target not in targets:
        return None
    intents = sem_v2._deterministic_intents(action, target)
    direct = branch._state_service_intent(service)
    if direct:
        intents.add(direct)
    return next(iter(intents)) if len(intents) == 1 else None


def _path_profiles(record, target):
    effective = record.get("effective") or {}
    top_conditions = effective.get("conditions", effective.get("condition", [])) if isinstance(effective, dict) else []
    top_numeric = _numeric_constraints(top_conditions)
    trigger_variants = _trigger_variants(effective)
    results = []

    def walk(sequence, inherited_conditions, branch_path):
        local_conditions = list(inherited_conditions)
        for index, action in enumerate(_as_list(sequence)):
            if not isinstance(action, dict):
                continue
            if "condition" in action and not any(k in action for k in ("service", "action", "choose", "if", "sequence")):
                local_conditions.append(action)
                continue
            if "choose" in action:
                for choice_index, choice in enumerate(_as_list(action.get("choose"))):
                    if not isinstance(choice, dict):
                        continue
                    cond = choice.get("conditions", choice.get("condition", []))
                    walk(choice.get("sequence", []), local_conditions + _as_list(cond), branch_path + [f"choose[{index}:{choice_index}]"])
                if action.get("default") is not None:
                    walk(action.get("default"), list(local_conditions), branch_path + [f"choose[{index}:default]"])
                continue
            if "if" in action:
                walk(action.get("then", []), local_conditions + _as_list(action.get("if", [])), branch_path + [f"if[{index}:then]"])
                if action.get("else") is not None:
                    walk(action.get("else"), list(local_conditions), branch_path + [f"if[{index}:else]"])
                continue
            if "sequence" in action and not any(k in action for k in ("service", "action")):
                walk(action.get("sequence"), list(local_conditions), branch_path + [f"sequence[{index}]"])
                continue

            intent = _service_intent(action, target)
            if not intent:
                continue
            branch_numeric = top_numeric + _numeric_constraints(local_conditions)
            allowed_ids = _trigger_condition_ids(local_conditions)
            variants = [x for x in trigger_variants if not allowed_ids or x["id"] in allowed_ids]
            if not variants:
                variants = [{"id": None, "numeric": [], "platform": None}]
            for variant in variants:
                results.append({
                    "intent": intent,
                    "trigger_id": variant.get("id"),
                    "trigger_platform": variant.get("platform"),
                    "numeric": branch_numeric + list(variant.get("numeric") or []),
                    "branch_path": list(branch_path),
                })

    actions = effective.get("actions", effective.get("action", [])) if isinstance(effective, dict) else []
    walk(actions, [], [])
    return results


def _range_map(constraints):
    result = {}
    for item in constraints or []:
        if not isinstance(item, dict) or not item.get("entity_id"):
            continue
        entity = str(item["entity_id"])
        slot = result.setdefault(entity, {"above": None, "below": None})
        above = _number(item.get("above")); below = _number(item.get("below"))
        if above is not None:
            slot["above"] = above if slot["above"] is None else max(slot["above"], above)
        if below is not None:
            slot["below"] = below if slot["below"] is None else min(slot["below"], below)
    return result


def _pair_numeric_relation(path_a, path_b):
    a = _range_map(path_a.get("numeric")); b = _range_map(path_b.get("numeric"))
    common = sorted(set(a) & set(b))
    overlaps = []; disjoint = []
    for entity in common:
        low_values = [x for x in (a[entity].get("above"), b[entity].get("above")) if x is not None]
        high_values = [x for x in (a[entity].get("below"), b[entity].get("below")) if x is not None]
        low = max(low_values) if low_values else None
        high = min(high_values) if high_values else None
        if low is not None and high is not None and low >= high:
            disjoint.append({"entity_id": entity, "reason": "literal_numeric_ranges_disjoint", "lower_bound": low, "upper_bound": high})
        else:
            overlaps.append({"entity_id": entity, "above": low, "below": high, "reason": "literal_numeric_policy_window_overlap"})
    return {"common_entities": common, "overlaps": overlaps, "disjoint": disjoint}


def _analyze_pair(pair, by_alias):
    target = str(pair.get("entity_id") or "")
    aliases = [str(x) for x in pair.get("automations") or []]
    if architecture_base._kind(target) != "actuator" or len(aliases) != 2:
        return None
    records_a = by_alias.get(aliases[0]) or []; records_b = by_alias.get(aliases[1]) or []
    if len(records_a) != 1 or len(records_b) != 1:
        return {"status": "insufficient_static_identity", "conflicts": [], "safe_pairs": []}
    paths_a = _path_profiles(records_a[0], target); paths_b = _path_profiles(records_b[0], target)
    opposing = [(a, b) for a in paths_a for b in paths_b if a.get("intent") != b.get("intent")]
    conflicts = []; safe = []
    for a, b in opposing:
        relation = _pair_numeric_relation(a, b)
        sample = {
            "intent_a": a.get("intent"), "intent_b": b.get("intent"),
            "trigger_a": a.get("trigger_id"), "trigger_b": b.get("trigger_id"),
            "branch_a": a.get("branch_path"), "branch_b": b.get("branch_path"),
            "common_numeric_entities": relation["common_entities"],
        }
        if relation["disjoint"]:
            safe.append({**sample, "disjoint_evidence": relation["disjoint"][:4]})
        else:
            conflicts.append({**sample, "overlap_evidence": relation["overlaps"][:6]})
    return {
        "model": POLICY_CONFLICT_MODEL,
        "status": "policy_overlap" if conflicts else ("numeric_exclusion" if opposing else "equivalent_intents"),
        "opposing_path_pair_count": len(opposing),
        "conflict_path_pair_count": len(conflicts),
        "numerically_disjoint_path_pair_count": len(safe),
        "conflicts": conflicts[:8],
        "safe_pairs": safe[:8],
        "templates_executed": False,
        "simultaneous_execution_proven": False,
        "policy": "resolve_only_if_every_opposing_path_is_statically_disjoint",
    }


def _pair_key(pair):
    return (str(pair.get("entity_id") or ""), frozenset(str(x) for x in pair.get("automations") or []))


def refine_condition_semantics_v9(report):
    current = base.refine_condition_semantics_v8(report)
    by_alias, parse_errors = sem_v1.effective_automation_map(report)
    newly_resolved = []; remaining = []; resolved_keys = set(); policy_overlap_count = 0
    for raw in current.get("unproven_pairs") or []:
        if not isinstance(raw, dict) or architecture_base._kind(str(raw.get("entity_id") or "")) != "actuator":
            remaining.append(raw); continue
        analysis = _analyze_pair(raw, by_alias)
        if not analysis:
            remaining.append(raw); continue
        if analysis.get("status") == "numeric_exclusion" and analysis.get("opposing_path_pair_count", 0) > 0:
            newly_resolved.append({
                "entity_id": raw.get("entity_id"), "automations": raw.get("automations") or [],
                "reason": "branch_numeric_exclusion", "proof_type": "exclusive",
                "semantic_layer": "v9_branch_policy", "target_kind": "actuator",
                "confidence": "high", "evidence": analysis,
            })
            resolved_keys.add(_pair_key(raw))
        else:
            enriched = dict(raw); enriched["v9_policy_analysis"] = analysis
            if analysis.get("status") == "policy_overlap":
                policy_overlap_count += 1
                enriched["review_priority"] = "high"
                enriched["evidence_level"] = "probable"
                enriched["policy_overlap_proven"] = True
            remaining.append(enriched)
    if resolved_keys:
        try:
            sem_v6._sync_finding_examples(report, resolved_keys)
        except Exception:
            pass
    physical = [x for x in remaining if isinstance(x, dict) and architecture_base._kind(str(x.get("entity_id") or "")) == "actuator"]
    helpers = [x for x in remaining if isinstance(x, dict) and architecture_base._kind(str(x.get("entity_id") or "")) == "helper"]
    other = [x for x in remaining if isinstance(x, dict) and architecture_base._kind(str(x.get("entity_id") or "")) not in {"actuator", "helper"}]
    result = {
        **current,
        "model": CONDITION_MODEL,
        "unproven_pairs": remaining,
        "unproven_pair_count": len(remaining),
        "physical_unproven_pair_count": len(physical),
        "helper_unproven_pair_count": len(helpers),
        "other_unproven_pair_count": len(other),
        "resolved_pair_count": int(current.get("resolved_pair_count", 0) or 0) + len(newly_resolved),
        "proven_exclusive_pair_count": int(current.get("proven_exclusive_pair_count", 0) or 0) + len(newly_resolved),
        "branch_numeric_resolved_pair_count": len(newly_resolved),
        "branch_numeric_resolutions": newly_resolved[:12],
        "policy_overlap_pair_count": policy_overlap_count,
        "v9_parse_error_count": len(parse_errors or []),
        "v9_policy": "branch_trigger_constraints_without_template_execution",
    }
    report["condition_semantics"] = result
    return result
