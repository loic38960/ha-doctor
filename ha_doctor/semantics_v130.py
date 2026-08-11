"""HA Doctor 0.13 controller semantics.

V8 adds a conservative mandatory-guard matrix on top of V7. A remaining
physical controller pair is resolved only when both automations have mandatory,
literal state guards on the same entity and those accepted state sets are
disjoint. This is a proof of mutual exclusion, not a heuristic.
"""

import intelligence_v080 as architecture_base
import semantics_v081 as sem_v1
import semantics_v088 as sem_v6
import semantics_v100 as base
from contracts_v130 import CONDITION_MODEL


def _as_state_map(value):
    result = {}
    for entity, states in (value or {}).items():
        vals = {str(x) for x in (states or ()) if x is not None}
        if vals:
            result[str(entity)] = vals
    return result


def _mandatory_state_guards(record):
    effective = record.get("effective") or {}
    conditions = effective.get("conditions", effective.get("condition", [])) if isinstance(effective, dict) else []
    return _as_state_map(sem_v6.enhanced_required_state_guards(conditions))


def disjoint_mandatory_guard_evidence(guards_a, guards_b):
    """Return literal mandatory guard proofs that make simultaneous execution impossible."""
    a = _as_state_map(guards_a)
    b = _as_state_map(guards_b)
    proofs = []
    for entity in sorted(set(a) & set(b)):
        states_a = set(a[entity])
        states_b = set(b[entity])
        if states_a and states_b and states_a.isdisjoint(states_b):
            proofs.append({
                "entity_id": entity,
                "automation_a_states": sorted(states_a),
                "automation_b_states": sorted(states_b),
                "intersection": [],
                "reason": "mandatory_literal_state_guards_are_disjoint",
            })
    return proofs


def _pair_key(pair):
    return (
        str(pair.get("entity_id") or ""),
        frozenset(str(x) for x in pair.get("automations") or []),
    )


def _annotate_or_resolve(pair, by_alias):
    target = str(pair.get("entity_id") or "")
    aliases = [str(x) for x in pair.get("automations") or []]
    if architecture_base._kind(target) != "actuator" or len(aliases) != 2:
        return None, pair
    records_a = by_alias.get(aliases[0]) or []
    records_b = by_alias.get(aliases[1]) or []
    if len(records_a) != 1 or len(records_b) != 1:
        enriched = dict(pair)
        enriched["v8_guard_matrix"] = {"status": "insufficient_static_identity", "proof_count": 0}
        return None, enriched

    guards_a = _mandatory_state_guards(records_a[0])
    guards_b = _mandatory_state_guards(records_b[0])
    proofs = disjoint_mandatory_guard_evidence(guards_a, guards_b)
    matrix = {
        "model": CONDITION_MODEL,
        "automation_a": {"alias": aliases[0], "mandatory_state_guards": {k: sorted(v) for k, v in guards_a.items()}},
        "automation_b": {"alias": aliases[1], "mandatory_state_guards": {k: sorted(v) for k, v in guards_b.items()}},
        "common_guard_entity_count": len(set(guards_a) & set(guards_b)),
        "proof_count": len(proofs),
        "proofs": proofs[:6],
        "templates_executed": False,
        "policy": "resolve_only_with_disjoint_mandatory_literal_guards",
    }
    if proofs:
        resolved = {
            "entity_id": target,
            "automations": aliases,
            "reason": "mandatory_state_guard_exclusion",
            "proof_type": "exclusive",
            "semantic_layer": "v8_mandatory_guard_matrix",
            "evidence": matrix,
            "target_kind": "actuator",
            "confidence": "high",
        }
        return resolved, None

    enriched = dict(pair)
    enriched["v8_guard_matrix"] = {**matrix, "status": "review"}
    return None, enriched


def refine_condition_semantics_v8(report):
    current = base.refine_condition_semantics_v7(report)
    by_alias, parse_errors = sem_v1.effective_automation_map(report)
    newly_resolved = []
    remaining = []
    resolved_keys = set()

    for raw in current.get("unproven_pairs") or []:
        if not isinstance(raw, dict):
            remaining.append(raw)
            continue
        resolved, unresolved = _annotate_or_resolve(raw, by_alias)
        if resolved:
            newly_resolved.append(resolved)
            resolved_keys.add(_pair_key(raw))
        else:
            remaining.append(unresolved)

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
        "mandatory_guard_resolved_pair_count": len(newly_resolved),
        "mandatory_guard_resolutions": newly_resolved[:12],
        "v8_guard_matrix_review_pair_count": sum(1 for x in remaining if isinstance(x, dict) and x.get("v8_guard_matrix")),
        "v8_parse_error_count": len(parse_errors or []),
        "v8_policy": "proof_first_mandatory_guard_exclusion",
    }
    report["condition_semantics"] = result
    return result
