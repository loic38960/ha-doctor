"""HA Doctor 0.8.8 controller semantics.

V6 adds three high-confidence proofs on top of the validated 0.8.5 branch engine:
- literal state-membership guards in Jinja templates;
- immediate supervisory interlocks (target transition -> guarded corrective command);
- third-party mediated interlocks that enforce a phase established by another controller.

The layer is read-only and never executes templates.
"""
from collections import defaultdict
import re

import intelligence_v080 as architecture_base
import semantics_v081 as sem_v1
import semantics_v085 as branch
import semantics_v085_fixed as hardened

VERSION = "0.8.8"
CONDITION_MODEL = "condition_semantics_v6_supervisory_interlocks"

_STATES_IN_RE = re.compile(
    r"""states\(\s*['\"](?P<entity>[a-z0-9_]+\.[a-z0-9_]+)['\"]\s*\)\s*in\s*\[(?P<values>[^\]]+)\]""",
    re.IGNORECASE,
)
_QUOTED_RE = re.compile(r"""['\"]([^'\"]+)['\"]""")
_BLOCKING_KEYS = {"delay", "wait_template", "wait_for_trigger", "wait_variable"}


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _merge_guards(target, source):
    for entity_id, states in (source or {}).items():
        target.setdefault(str(entity_id), set()).update(str(x) for x in (states or ()))


def _literal_membership_guards(text):
    """Extract only positive, literal membership guards that are mandatory."""
    result = defaultdict(set)
    if not isinstance(text, str):
        return {}
    lowered = text.lower()
    if " or " in lowered or re.search(r"\bnot\s*(?:\(|states\s*\()", lowered):
        return {}
    for match in _STATES_IN_RE.finditer(text):
        values = [item for item in _QUOTED_RE.findall(match.group("values") or "") if item]
        if values:
            result[match.group("entity").lower()].update(values)
    return dict(result)


_ORIGINAL_REQUIRED_GUARDS = sem_v1.required_state_guards


def enhanced_required_state_guards(value):
    """Preserve V1 guarantees and add literal ``states(entity) in [...]``."""
    result = defaultdict(set)
    _merge_guards(result, _ORIGINAL_REQUIRED_GUARDS(value))

    if isinstance(value, str):
        _merge_guards(result, _literal_membership_guards(value))
        return dict(result)
    if isinstance(value, list):
        for item in value:
            _merge_guards(result, enhanced_required_state_guards(item))
        return dict(result)
    if not isinstance(value, dict):
        return dict(result)

    kind = str(value.get("condition") or "").lower()
    if kind in {"or", "not"}:
        return dict(result)
    for child in value.values():
        if isinstance(child, (dict, list, str)):
            _merge_guards(result, enhanced_required_state_guards(child))
    return dict(result)


def _with_enhanced_guards(func, *args, **kwargs):
    original = sem_v1.required_state_guards
    sem_v1.required_state_guards = enhanced_required_state_guards
    try:
        return func(*args, **kwargs)
    finally:
        sem_v1.required_state_guards = original


def _paths(record, target_entity):
    effective = record.get("effective") or {}
    return _with_enhanced_guards(branch._extract_paths, effective, target_entity)


def _triggers(record):
    return branch._trigger_states(record.get("effective") or {})


def _state_from_intent(intent):
    value = str(intent or "")
    if value.startswith("state:"):
        return value.split(":", 1)[1]
    return None


def _service_target_intent(action, target_entity):
    service, targets = branch._service_and_targets(action)
    if target_entity not in targets:
        return None
    intents = branch.sem_v2._deterministic_intents(action, target_entity)
    direct = branch._state_service_intent(service)
    if direct:
        intents.add(direct)
    return next(iter(intents)) if len(intents) == 1 else None


def _target_commands_with_blocking(effective, target_entity):
    """Return deterministic target commands and whether a wait preceded them."""
    found = []

    def walk(sequence, blocked=False):
        local_blocked = bool(blocked)
        for action in _as_list(sequence):
            if not isinstance(action, dict):
                continue
            if any(key in action for key in _BLOCKING_KEYS):
                local_blocked = True
                continue

            if "choose" in action:
                for choice in _as_list(action.get("choose")):
                    if isinstance(choice, dict):
                        walk(choice.get("sequence"), local_blocked)
                if action.get("default") is not None:
                    walk(action.get("default"), local_blocked)
                continue

            if "if" in action:
                walk(action.get("then"), local_blocked)
                if action.get("else") is not None:
                    walk(action.get("else"), local_blocked)
                continue

            if "sequence" in action and not any(key in action for key in ("service", "action")):
                walk(action.get("sequence"), local_blocked)
                continue

            intent = _service_target_intent(action, target_entity)
            if intent:
                found.append({"intent": intent, "blocked_before": local_blocked})

    actions = effective.get("actions", effective.get("action", [])) if isinstance(effective, dict) else []
    walk(actions, False)
    return found


def supervisory_interlock_profile(record, target_entity):
    """Recognise an immediate guarded corrective interlock on the target."""
    trigger = _triggers(record).get(target_entity) or {}
    to_states = set(str(x) for x in trigger.get("to") or ())
    if len(to_states) != 1:
        return None
    trigger_state = next(iter(to_states))
    expected = {"on": "state:off", "off": "state:on"}.get(trigger_state)
    if not expected:
        return None

    commands = _target_commands_with_blocking(record.get("effective") or {}, target_entity)
    if not commands or any(item.get("blocked_before") for item in commands):
        return None
    if any(item.get("intent") != expected for item in commands):
        return None

    paths = _paths(record, target_entity)
    if not paths:
        return None
    path_guards = []
    for path in paths:
        guards = {
            str(entity): set(str(x) for x in states)
            for entity, states in (path.get("guards") or {}).items()
            if str(entity) != str(target_entity)
        }
        if not guards:
            return None
        path_guards.append(guards)

    common = {}
    entities = set.intersection(*(set(item) for item in path_guards)) if path_guards else set()
    for entity in sorted(entities):
        states = set.intersection(*(set(item.get(entity) or ()) for item in path_guards))
        if states:
            common[entity] = states
    if not common:
        return None

    return {
        "reason": "supervisory_interlock",
        "trigger_state": trigger_state,
        "command_intent": expected,
        "guards": {entity: sorted(states) for entity, states in common.items()},
    }


def _enhanced_direct_resolution(record_a, record_b, target_entity):
    resolution = _with_enhanced_guards(hardened.resolve_branch_pair, record_a, record_b, target_entity)
    if not resolution:
        return None

    mechanisms = set((resolution.get("evidence") or {}).get("mechanisms") or [])
    proof_type = "exclusive" if "branch_disjoint_state_guards" in mechanisms else "coordinated"
    return {
        **resolution,
        "proof_type": proof_type,
        "semantic_layer": "v6_membership_guards" if proof_type == "exclusive" else "v5_branch",
    }


def _interlock_pair_resolution(record_a, record_b, target_entity):
    profile_a = supervisory_interlock_profile(record_a, target_entity)
    profile_b = supervisory_interlock_profile(record_b, target_entity)
    profiles = [item for item in (profile_a, profile_b) if item]
    if not profiles:
        return None
    profile = profiles[0]
    return {
        "reason": "supervisory_interlock",
        "proof_type": "coordinated",
        "semantic_layer": "v6_supervisory_interlock",
        "evidence": profile,
    }


def _guard_matches_prior_write(profile, path):
    guards = profile.get("guards") or {}
    prior = path.get("prior_writes") or {}
    for entity, states in guards.items():
        if entity not in prior:
            continue
        if str(prior[entity]) in {str(x) for x in states}:
            return {"helper": entity, "phase_state": str(prior[entity])}
    return None


def _mediated_resolution(record_a, record_b, target_entity, all_records):
    paths_a = _paths(record_a, target_entity)
    paths_b = _paths(record_b, target_entity)
    if not paths_a or not paths_b:
        return None

    mediators = []
    for alias, record in all_records:
        if record is record_a or record is record_b:
            continue
        profile = supervisory_interlock_profile(record, target_entity)
        if profile:
            mediators.append((alias, profile))

    opposing = [
        (path_a, path_b)
        for path_a in paths_a
        for path_b in paths_b
        if path_a.get("intent") != path_b.get("intent")
    ]
    if not opposing:
        return None

    proofs = []
    for path_a, path_b in opposing:
        state_a = _state_from_intent(path_a.get("intent"))
        state_b = _state_from_intent(path_b.get("intent"))
        proof = None
        for alias, profile in mediators:
            trigger_state = str(profile.get("trigger_state") or "")
            command_state = _state_from_intent(profile.get("command_intent"))

            if state_a and state_b and command_state == state_a and trigger_state == state_b:
                phase = _guard_matches_prior_write(profile, path_a)
                if phase:
                    proof = {
                        "mediator": alias,
                        "protected_intent": path_a.get("intent"),
                        "intercepted_intent": path_b.get("intent"),
                        **phase,
                    }
                    break

            if state_a and state_b and command_state == state_b and trigger_state == state_a:
                phase = _guard_matches_prior_write(profile, path_b)
                if phase:
                    proof = {
                        "mediator": alias,
                        "protected_intent": path_b.get("intent"),
                        "intercepted_intent": path_a.get("intent"),
                        **phase,
                    }
                    break
        if not proof:
            return None
        proofs.append(proof)

    return {
        "reason": "mediated_supervisory_interlock",
        "proof_type": "coordinated",
        "semantic_layer": "v6_mediated_interlock",
        "evidence": {
            "opposing_path_count": len(opposing),
            "proof_count": len(proofs),
            "examples": proofs[:4],
        },
    }


def resolve_pair_v6(record_a, record_b, target_entity, all_records=None):
    direct = _enhanced_direct_resolution(record_a, record_b, target_entity)
    if direct:
        return direct

    interlock = _interlock_pair_resolution(record_a, record_b, target_entity)
    if interlock:
        return interlock

    if all_records:
        mediated = _mediated_resolution(record_a, record_b, target_entity, all_records)
        if mediated:
            return mediated
    return None


def _all_unique_records(by_alias):
    result = []
    for alias, records in (by_alias or {}).items():
        if len(records) == 1:
            result.append((str(alias), records[0]))
    return result


def _sync_finding_examples(report, resolved_keys):
    finding = next(
        (item for item in report.get("findings") or [] if item.get("rule_id") == "HD-AUTO-003"),
        None,
    )
    if not finding:
        return
    refined = []
    for raw in finding.get("examples") or []:
        if not isinstance(raw, dict):
            continue
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


def refine_condition_semantics_v6(report):
    current = dict(report.get("condition_semantics") or {})
    by_alias, parse_errors = sem_v1.effective_automation_map(report)
    all_records = _all_unique_records(by_alias)

    newly_resolved = []
    remaining = []
    exclusive_added = 0
    coordinated_added = 0
    supervisory_count = 0
    mediated_count = 0
    membership_count = 0

    for pair in current.get("unproven_pairs") or []:
        if not isinstance(pair, dict):
            remaining.append(pair)
            continue
        target = str(pair.get("entity_id") or "")
        automations = [str(x) for x in pair.get("automations") or []]
        if architecture_base._kind(target) != "actuator" or len(automations) != 2:
            remaining.append(pair)
            continue

        records_a = by_alias.get(automations[0]) or []
        records_b = by_alias.get(automations[1]) or []
        resolution = None
        if len(records_a) == 1 and len(records_b) == 1:
            resolution = resolve_pair_v6(records_a[0], records_b[0], target, all_records=all_records)
        if not resolution:
            remaining.append(pair)
            continue

        proof_type = str(resolution.get("proof_type") or "coordinated")
        if proof_type == "exclusive":
            exclusive_added += 1
            membership_count += 1
        else:
            coordinated_added += 1
            if resolution.get("reason") == "supervisory_interlock":
                supervisory_count += 1
            elif resolution.get("reason") == "mediated_supervisory_interlock":
                mediated_count += 1

        newly_resolved.append({
            "entity_id": target,
            "automations": automations,
            "reason": resolution.get("reason"),
            "proof_type": proof_type,
            "semantic_layer": resolution.get("semantic_layer"),
            "evidence": resolution.get("evidence") or {},
            "target_kind": "actuator",
            "confidence": "high",
        })

    physical = [
        item for item in remaining
        if isinstance(item, dict) and architecture_base._kind(str(item.get("entity_id") or "")) == "actuator"
    ]
    helpers = [
        item for item in remaining
        if isinstance(item, dict) and architecture_base._kind(str(item.get("entity_id") or "")) == "helper"
    ]
    other = [
        item for item in remaining
        if isinstance(item, dict) and architecture_base._kind(str(item.get("entity_id") or "")) not in {"actuator", "helper"}
    ]

    previous_resolved = int(current.get("resolved_pair_count", 0) or 0)
    previous_exclusive = int(current.get("proven_exclusive_pair_count", 0) or 0)
    previous_coordinated = int(current.get("coordinated_pair_count", 0) or 0)
    previous_protocol = int(current.get("protocol_coordinated_pair_count", 0) or 0)
    existing_protocol_pairs = list(current.get("protocol_coordinated_pairs") or [])

    coordinated_new_pairs = [item for item in newly_resolved if item["proof_type"] == "coordinated"]
    result = {
        **current,
        "model": CONDITION_MODEL,
        "pre_v6_unproven_pair_count": int(current.get("unproven_pair_count", 0) or 0),
        "pre_v6_physical_unproven_pair_count": int(current.get("physical_unproven_pair_count", 0) or 0),
        "semantic_v6_resolved_pair_count": len(newly_resolved),
        "semantic_v6_resolved_pairs": newly_resolved[:40],
        "membership_exclusive_pair_count": membership_count,
        "supervisory_interlock_pair_count": supervisory_count,
        "mediated_interlock_pair_count": mediated_count,
        "proven_exclusive_pair_count": previous_exclusive + exclusive_added,
        "coordinated_pair_count": previous_coordinated + coordinated_added,
        "protocol_coordinated_pair_count": previous_protocol + coordinated_added,
        "protocol_coordinated_pairs": (existing_protocol_pairs + coordinated_new_pairs)[:60],
        "resolved_pair_count": previous_resolved + len(newly_resolved),
        "unproven_pair_count": len(remaining),
        "unproven_pairs": remaining[:60],
        "physical_unproven_pair_count": len(physical),
        "helper_unproven_pair_count": len(helpers),
        "other_unproven_pair_count": len(other),
        "parse_errors": (current.get("parse_errors") or parse_errors or [])[:12],
        "confidence": "high_for_literal_guards_and_supervisory_interlocks",
        "note": (
            "V6 ajoute les ensembles d'états littéraux, les interlocks correctifs immédiats "
            "et les protocoles arbitrés par un troisième contrôleur. Une paire n'est retirée "
            "que lorsqu'une preuve déterministe couvre tous les chemins opposés."
        ),
    }
    report["condition_semantics"] = result

    resolved_keys = {
        (str(item.get("entity_id") or ""), frozenset(str(x) for x in item.get("automations") or []))
        for item in newly_resolved
    }
    _sync_finding_examples(report, resolved_keys)
    return result
