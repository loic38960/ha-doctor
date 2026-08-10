"""HA Doctor 0.8.5 branch-aware controller semantics.

This layer refines only controller pairs that 0.8.4 could not prove safe. It
never executes templates. Instead it follows deterministic action paths and
recognises explicit helper phase markers, state guards and state-transition
handoffs. A pair is resolved only when every opposing deterministic command
path is separated by high-confidence phase evidence.
"""
from collections import defaultdict

import intelligence_v080 as architecture_base
import semantics_v081 as sem_v1
import semantics_v082 as sem_v2

VERSION = "0.8.5"
CONDITION_MODEL = "condition_semantics_v5_branch_protocols"


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _copy_guards(guards):
    return {str(entity): set(str(x) for x in states) for entity, states in (guards or {}).items()}


def _merge_guards(base, extra):
    result = _copy_guards(base)
    for entity, states in (extra or {}).items():
        result.setdefault(str(entity), set()).update(str(x) for x in states)
    return result


def _state_service_intent(service):
    service = str(service or "").lower()
    if service.endswith(".turn_on"):
        return "state:on"
    if service.endswith(".turn_off"):
        return "state:off"
    if service.endswith(".open_cover"):
        return "cover:open"
    if service.endswith(".close_cover"):
        return "cover:closed"
    return None


def _service_and_targets(action):
    if not isinstance(action, dict):
        return None, set()
    service = action.get("service")
    if not isinstance(service, str):
        raw = action.get("action")
        service = raw if isinstance(raw, str) and "." in raw else None
    if not service:
        return None, set()
    targets = set()
    target = action.get("target") or {}
    data = action.get("data") or {}
    if isinstance(target, dict):
        targets.update(sem_v2._entity_ids(target.get("entity_id")))
    if isinstance(data, dict):
        targets.update(sem_v2._entity_ids(data.get("entity_id")))
    return service, {str(x) for x in targets}


def _trigger_states(effective):
    """Return explicit state transition evidence keyed by entity."""
    result = defaultdict(lambda: {"to": set(), "from": set()})
    for trigger in sem_v2._trigger_list(effective):
        if not isinstance(trigger, dict):
            continue
        platform = str(trigger.get("platform") or trigger.get("trigger") or "").lower()
        if platform != "state":
            continue
        entities = sem_v2._entity_ids(trigger.get("entity_id"))
        for entity in entities:
            for key in ("to", "from"):
                raw = trigger.get(key)
                if isinstance(raw, (str, int, float, bool)):
                    result[str(entity)][key].add(str(raw))
    return {entity: {key: set(values) for key, values in states.items()} for entity, states in result.items()}


def _extract_paths(effective, target_entity):
    """Collect deterministic commands on target with guards and prior writes.

    ``prior_writes`` is deliberately limited to deterministic state commands
    already executed in the same sequential path. It gives strong evidence for
    helper-mediated handoffs without pretending to understand arbitrary Jinja.
    """
    paths = []
    top_conditions = effective.get("conditions", effective.get("condition", [])) if isinstance(effective, dict) else []
    initial_guards = sem_v1.required_state_guards(top_conditions)

    def walk_sequence(sequence, guards, prior_writes, branch_path):
        current_guards = _copy_guards(guards)
        current_writes = dict(prior_writes or {})
        for index, action in enumerate(_as_list(sequence)):
            if not isinstance(action, dict):
                continue

            # A condition action gates every subsequent action in this sequence.
            if "condition" in action and not any(key in action for key in ("service", "action", "choose", "if", "sequence")):
                current_guards = _merge_guards(current_guards, sem_v1.required_state_guards(action))
                continue

            if "choose" in action:
                for choice_index, choice in enumerate(_as_list(action.get("choose"))):
                    if not isinstance(choice, dict):
                        continue
                    branch_guards = _merge_guards(
                        current_guards,
                        sem_v1.required_state_guards(choice.get("conditions", choice.get("condition", []))),
                    )
                    walk_sequence(
                        choice.get("sequence", []), branch_guards, dict(current_writes),
                        branch_path + [f"choose[{index}:{choice_index}]"],
                    )
                if action.get("default") is not None:
                    walk_sequence(
                        action.get("default"), current_guards, dict(current_writes),
                        branch_path + [f"choose[{index}:default]"],
                    )
                continue

            if "if" in action:
                branch_guards = _merge_guards(
                    current_guards,
                    sem_v1.required_state_guards(action.get("if", [])),
                )
                walk_sequence(
                    action.get("then", []), branch_guards, dict(current_writes),
                    branch_path + [f"if[{index}:then]"],
                )
                # NOT of an arbitrary HA condition is not promoted as evidence.
                if action.get("else") is not None:
                    walk_sequence(
                        action.get("else"), current_guards, dict(current_writes),
                        branch_path + [f"if[{index}:else]"],
                    )
                continue

            # Explicit nested sequence wrappers.
            if "sequence" in action and not any(key in action for key in ("service", "action")):
                walk_sequence(
                    action.get("sequence"), current_guards, dict(current_writes),
                    branch_path + [f"sequence[{index}]"],
                )
                continue

            service, targets = _service_and_targets(action)
            intent = _state_service_intent(service)
            if service and target_entity in targets:
                # Reuse the older deterministic parser for select/number/climate
                # commands while keeping state services cheap and explicit.
                intents = sem_v2._deterministic_intents(action, target_entity)
                if intent:
                    intents.add(intent)
                if len(intents) == 1:
                    paths.append({
                        "intent": next(iter(intents)),
                        "guards": {k: sorted(v) for k, v in current_guards.items()},
                        "prior_writes": dict(current_writes),
                        "branch_path": list(branch_path),
                    })

            # Deterministic writes become phase markers for later actions.
            if service and intent and intent.startswith("state:"):
                state = intent.split(":", 1)[1]
                for entity in targets:
                    if architecture_base._kind(str(entity)) == "helper":
                        current_writes[str(entity)] = state

    actions = effective.get("actions", effective.get("action", [])) if isinstance(effective, dict) else []
    walk_sequence(actions, initial_guards, {}, [])
    return paths


def _guard_state(path, helper):
    states = set(str(x) for x in (path.get("guards") or {}).get(helper, []))
    return next(iter(states)) if len(states) == 1 else None


def _phase_evidence(path_a, trigger_a, path_b, trigger_b):
    """Return high-confidence evidence that two opposing paths are phase-separated."""
    guards_a = path_a.get("guards") or {}
    guards_b = path_b.get("guards") or {}
    exclusive = sem_v1._exclusive(guards_a, guards_b)
    if exclusive:
        return {"reason": "branch_disjoint_state_guards", "evidence": exclusive[:4]}

    helpers = set((path_a.get("prior_writes") or {})) | set((path_b.get("prior_writes") or {}))
    helpers |= set(guards_a) | set(guards_b) | set(trigger_a) | set(trigger_b)
    helpers = {h for h in helpers if architecture_base._kind(str(h)) == "helper"}

    for helper in sorted(helpers):
        prior_a = (path_a.get("prior_writes") or {}).get(helper)
        prior_b = (path_b.get("prior_writes") or {}).get(helper)
        guard_a = _guard_state(path_a, helper)
        guard_b = _guard_state(path_b, helper)
        to_a = set((trigger_a.get(helper) or {}).get("to") or ())
        to_b = set((trigger_b.get(helper) or {}).get("to") or ())

        # Sender explicitly establishes helper phase X before commanding the
        # target; receiver can only start when that helper later transitions Y.
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

        # Explicit guards or a guard plus a transition to the opposite state
        # are also safe phase separators.
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
    paths_a = _extract_paths(effective_a, target_entity)
    paths_b = _extract_paths(effective_b, target_entity)
    if not paths_a or not paths_b:
        return None

    trigger_a = _trigger_states(effective_a)
    trigger_b = _trigger_states(effective_b)
    opposing = []
    for path_a in paths_a:
        for path_b in paths_b:
            if path_a.get("intent") == path_b.get("intent"):
                continue
            opposing.append((path_a, path_b))
    if not opposing:
        return {
            "reason": "all_branch_commands_equivalent",
            "evidence": {"path_count_a": len(paths_a), "path_count_b": len(paths_b)},
        }

    proofs = []
    for path_a, path_b in opposing:
        proof = _phase_evidence(path_a, trigger_a, path_b, trigger_b)
        if not proof:
            return None
        proofs.append(proof)

    reasons = sorted(set(str(item.get("reason")) for item in proofs))
    return {
        "reason": "branch_phase_protocol",
        "evidence": {
            "proof_count": len(proofs),
            "opposing_path_count": len(opposing),
            "mechanisms": reasons,
            "examples": [item.get("evidence") for item in proofs[:4]],
        },
    }


def build_condition_semantics_v5(report):
    current = report.get("condition_semantics") or {}
    by_alias, parse_errors = sem_v1.effective_automation_map(report)

    resolved = []
    remaining = []
    for pair in current.get("unproven_pairs") or []:
        target = str(pair.get("entity_id") or "")
        automations = [str(x) for x in pair.get("automations") or []]
        if architecture_base._kind(target) != "actuator" or len(automations) != 2:
            remaining.append(pair)
            continue
        records_a = by_alias.get(automations[0]) or []
        records_b = by_alias.get(automations[1]) or []
        resolution = None
        if len(records_a) == 1 and len(records_b) == 1:
            resolution = resolve_branch_pair(records_a[0], records_b[0], target)
        if not resolution:
            remaining.append(pair)
            continue
        resolved.append({
            "entity_id": target,
            "automations": automations,
            "reason": resolution["reason"],
            "evidence": resolution.get("evidence") or {},
            "target_kind": "actuator",
            "confidence": "high",
        })

    physical = [item for item in remaining if architecture_base._kind(str(item.get("entity_id") or "")) == "actuator"]
    helpers = [item for item in remaining if architecture_base._kind(str(item.get("entity_id") or "")) == "helper"]
    other = [item for item in remaining if architecture_base._kind(str(item.get("entity_id") or "")) not in {"actuator", "helper"}]
    previous_protocol = list(current.get("protocol_coordinated_pairs") or [])
    all_protocol = previous_protocol + resolved
    previous_resolved = int(current.get("resolved_pair_count", 0) or 0)

    result = {
        **current,
        "model": CONDITION_MODEL,
        "branch_protocol_resolved_pair_count": len(resolved),
        "branch_protocol_resolved_pairs": resolved[:40],
        "protocol_coordinated_pair_count": len(all_protocol),
        "protocol_coordinated_pairs": all_protocol[:60],
        "resolved_pair_count": previous_resolved + len(resolved),
        "unproven_pair_count": len(remaining),
        "unproven_pairs": remaining[:60],
        "physical_unproven_pair_count": len(physical),
        "helper_unproven_pair_count": len(helpers),
        "other_unproven_pair_count": len(other),
        "parse_errors": (current.get("parse_errors") or parse_errors or [])[:12],
        "confidence": "high_for_branch_phase_protocols_only",
        "note": (
            "V5 suit les chemins d'action déterministes et les marqueurs de phase helper. "
            "Une paire n'est déclassée que si tous ses chemins de commandes opposées sont séparés par une preuve explicite."
        ),
    }
    report["condition_semantics"] = result

    resolved_keys = {
        (str(item.get("entity_id") or ""), frozenset(str(x) for x in item.get("automations") or []))
        for item in resolved
    }
    finding = next((x for x in report.get("findings") or [] if x.get("rule_id") == "HD-AUTO-003"), None)
    if finding:
        refined = []
        for raw in finding.get("examples") or []:
            example = dict(raw)
            entity = str(example.get("entity_id") or "")
            pairs = []
            for pair in example.get("unprotected_pairs") or []:
                key = (entity, frozenset(str(x) for x in pair))
                if key not in resolved_keys:
                    pairs.append(pair)
            example["unprotected_pairs"] = pairs
            example["unprotected_pair_count"] = len(pairs)
            if pairs:
                refined.append(example)
        finding["examples"] = refined
        finding["summary"] = (
            f"{len(physical)} paire(s) sur actionneur physique restent à vérifier, "
            f"{len(helpers)} paire(s) concernent seulement des helpers ; "
            f"{len(all_protocol)} handoff(s) de phase sont maintenant reconnus, dont {len(resolved)} par analyse de branche."
        )
        finding["recommendation"] = (
            "Examiner uniquement les paires physiques restantes. Les séquences dont les branches établissent "
            "explicitement un handoff de phase sont séparées des conflits réellement non prouvés."
        )

    for explanation in report.get("diagnostic_explanations") or []:
        if str(explanation.get("source_id") or "") != "HD-AUTO-003":
            continue
        explanation["diagnosis"] = (
            f"{len(physical)} paire(s) physique(s) restent non prouvées ; "
            f"{len(resolved)} paire(s) supplémentaires ont été expliquées par les chemins d'action et marqueurs de phase."
        )
        evidence = [item for item in explanation.get("evidence") or [] if item.get("type") != "branch_protocol"]
        evidence.append({
            "type": "branch_protocol",
            "label": "Protocoles de branche",
            "text": f"{len(resolved)} résolue(s) en V5 · {len(physical)} physique(s) encore à vérifier",
        })
        explanation["evidence"] = evidence[:12]

    report.setdefault("architecture_analysis", {}).update({
        "condition_semantics_model": CONDITION_MODEL,
        "branch_protocol_resolved_pair_count": len(resolved),
        "protocol_coordinated_pair_count": len(all_protocol),
        "physical_unproven_controller_pair_count": len(physical),
        "helper_unproven_controller_pair_count": len(helpers),
    })
    return result
