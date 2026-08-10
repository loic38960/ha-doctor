"""Safety overlay for HA Doctor 0.8.5 branch-aware controller semantics.

A controller's guard on the target actuator itself (for example pump=off before
turn_on) is not proof that two controllers are mutually exclusive. This overlay
removes the target actuator from exclusivity evidence while preserving helper
phase proofs.
"""
import semantics_v085 as base

VERSION = "0.8.5"
CONDITION_MODEL = base.CONDITION_MODEL


def _phase_evidence_safe(path_a, trigger_a, path_b, trigger_b, target_entity):
    guards_a = {k: v for k, v in (path_a.get("guards") or {}).items() if str(k) != str(target_entity)}
    guards_b = {k: v for k, v in (path_b.get("guards") or {}).items() if str(k) != str(target_entity)}
    exclusive = base.sem_v1._exclusive(guards_a, guards_b)
    if exclusive:
        return {"reason": "branch_disjoint_state_guards", "evidence": exclusive[:4]}

    helpers = set((path_a.get("prior_writes") or {})) | set((path_b.get("prior_writes") or {}))
    helpers |= set(guards_a) | set(guards_b) | set(trigger_a) | set(trigger_b)
    helpers = {h for h in helpers if base.architecture_base._kind(str(h)) == "helper"}

    for helper in sorted(helpers):
        prior_a = (path_a.get("prior_writes") or {}).get(helper)
        prior_b = (path_b.get("prior_writes") or {}).get(helper)
        guard_a = base._guard_state({**path_a, "guards": guards_a}, helper)
        guard_b = base._guard_state({**path_b, "guards": guards_b}, helper)
        to_a = set((trigger_a.get(helper) or {}).get("to") or ())
        to_b = set((trigger_b.get(helper) or {}).get("to") or ())

        if prior_a is not None and to_b and all(str(prior_a) != str(x) for x in to_b):
            return {
                "reason": "branch_helper_phase_handoff",
                "evidence": {"helper": helper, "sender_state": str(prior_a), "receiver_to": sorted(to_b), "direction": "a_to_b"},
            }
        if prior_b is not None and to_a and all(str(prior_b) != str(x) for x in to_a):
            return {
                "reason": "branch_helper_phase_handoff",
                "evidence": {"helper": helper, "sender_state": str(prior_b), "receiver_to": sorted(to_a), "direction": "b_to_a"},
            }
        if guard_a is not None and guard_b is not None and guard_a != guard_b:
            return {
                "reason": "helper_state_phase_guard",
                "evidence": {"helper": helper, "state_a": guard_a, "state_b": guard_b},
            }
        if guard_a is not None and to_b and all(str(guard_a) != str(x) for x in to_b):
            return {
                "reason": "helper_guard_to_transition_handoff",
                "evidence": {"helper": helper, "guard_a": guard_a, "trigger_b_to": sorted(to_b)},
            }
        if guard_b is not None and to_a and all(str(guard_b) != str(x) for x in to_a):
            return {
                "reason": "helper_guard_to_transition_handoff",
                "evidence": {"helper": helper, "guard_b": guard_b, "trigger_a_to": sorted(to_a)},
            }
    return None


def resolve_branch_pair(record_a, record_b, target_entity):
    effective_a = record_a.get("effective") or {}
    effective_b = record_b.get("effective") or {}
    paths_a = base._extract_paths(effective_a, target_entity)
    paths_b = base._extract_paths(effective_b, target_entity)
    if not paths_a or not paths_b:
        return None

    trigger_a = base._trigger_states(effective_a)
    trigger_b = base._trigger_states(effective_b)
    opposing = [
        (path_a, path_b)
        for path_a in paths_a
        for path_b in paths_b
        if path_a.get("intent") != path_b.get("intent")
    ]
    if not opposing:
        return {
            "reason": "all_branch_commands_equivalent",
            "evidence": {"path_count_a": len(paths_a), "path_count_b": len(paths_b)},
        }

    proofs = []
    for path_a, path_b in opposing:
        proof = _phase_evidence_safe(path_a, trigger_a, path_b, trigger_b, target_entity)
        if not proof:
            return None
        proofs.append(proof)
    return {
        "reason": "branch_phase_protocol",
        "evidence": {
            "proof_count": len(proofs),
            "opposing_path_count": len(opposing),
            "mechanisms": sorted(set(str(item.get("reason")) for item in proofs)),
            "examples": [item.get("evidence") for item in proofs[:4]],
        },
    }


# build_condition_semantics_v5 resolves through its module-global function.
base.resolve_branch_pair = resolve_branch_pair


def build_condition_semantics_v5(report):
    return base.build_condition_semantics_v5(report)
