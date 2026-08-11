"""HA Doctor 0.16 automation evidence precision.

This module classifies two broad findings without changing Home Assistant:
- automations triggered by an entity they also control;
- exact consecutive duplicate actions.

The goal is not to auto-dismiss them, but to distinguish state reassertion,
state-transition feedback, notification side effects and idempotent control
candidates so the Decision Engine can give a more precise manual review.
"""

import json
from semantics_v081 import effective_automation_map
import semantics_v082 as sem2
import semantics_v085 as branch
from contracts_v160 import LOOP_MODEL, DUPLICATE_MODEL


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        return repr(value)


def _service(action):
    service, _ = branch._service_and_targets(action)
    return str(service or "")


def _duplicate_kind(service):
    domain = service.split(".", 1)[0] if "." in service else ""
    call = service.split(".", 1)[1] if "." in service else ""
    if domain in {"notify", "persistent_notification"}:
        return "side_effect_duplicate"
    if domain == "script":
        return "repeated_script_call"
    if domain in {"switch", "light", "input_boolean", "homeassistant", "climate", "cover"} and call in {
        "turn_on", "turn_off", "open_cover", "close_cover", "lock", "unlock"
    }:
        return "idempotent_control_candidate"
    return "service_side_effect_unknown"


def _scan_duplicate_sequence(sequence, alias, path="action"):
    results = []
    seq = _as_list(sequence)
    for index in range(1, len(seq)):
        left, right = seq[index - 1], seq[index]
        if isinstance(left, dict) and isinstance(right, dict) and _canonical(left) == _canonical(right):
            service = _service(right)
            results.append({
                "automation": alias, "path": f"{path}[{index-1}:{index}]", "service": service,
                "classification": _duplicate_kind(service), "exact_duplicate": True,
                "automatic_removal_safe": False,
            })
    for index, action in enumerate(seq):
        if not isinstance(action, dict):
            continue
        if "choose" in action:
            for choice_index, choice in enumerate(_as_list(action.get("choose"))):
                if isinstance(choice, dict):
                    results.extend(_scan_duplicate_sequence(choice.get("sequence", []), alias, f"{path}[{index}].choose[{choice_index}]"))
            if action.get("default") is not None:
                results.extend(_scan_duplicate_sequence(action.get("default", []), alias, f"{path}[{index}].default"))
        if "if" in action:
            results.extend(_scan_duplicate_sequence(action.get("then", []), alias, f"{path}[{index}].then"))
            if action.get("else") is not None:
                results.extend(_scan_duplicate_sequence(action.get("else", []), alias, f"{path}[{index}].else"))
        if "sequence" in action and not _service(action):
            results.extend(_scan_duplicate_sequence(action.get("sequence", []), alias, f"{path}[{index}].sequence"))
    return results


def build_duplicate_semantics(report, automation_map=None):
    automation_map, parse_errors = (automation_map, []) if automation_map is not None else effective_automation_map(report)
    items = []
    for alias, records in (automation_map or {}).items():
        if len(records) != 1:
            continue
        effective = records[0].get("effective") or {}
        actions = effective.get("actions", effective.get("action", [])) if isinstance(effective, dict) else []
        items.extend(_scan_duplicate_sequence(actions, str(alias)))
    result = {
        "model": DUPLICATE_MODEL, "count": len(items), "items": items[:30],
        "side_effect_duplicate_count": sum(1 for x in items if x.get("classification") == "side_effect_duplicate"),
        "idempotent_control_candidate_count": sum(1 for x in items if x.get("classification") == "idempotent_control_candidate"),
        "repeated_script_call_count": sum(1 for x in items if x.get("classification") == "repeated_script_call"),
        "unknown_side_effect_count": sum(1 for x in items if x.get("classification") == "service_side_effect_unknown"),
        "parse_error_count": len(parse_errors or []), "automatic_cleanup": False,
    }
    report["duplicate_action_semantics"] = result
    return result


def _trigger_state_intents(effective, target):
    states = set()
    triggers = sem2._trigger_list(effective)
    for trigger in triggers:
        if not isinstance(trigger, dict) or target not in set(str(x) for x in sem2._entity_ids(trigger.get("entity_id"))):
            continue
        platform = str(trigger.get("platform") or trigger.get("trigger") or "").lower()
        if platform != "state":
            continue
        to = trigger.get("to")
        if isinstance(to, str) and to.lower() in {"on", "off"}:
            states.add(f"state:{to.lower()}")
    return states


def _action_intents(value, target):
    intents = set()
    if isinstance(value, list):
        for child in value:
            intents |= _action_intents(child, target)
        return intents
    if not isinstance(value, dict):
        return intents
    try:
        intents |= set(sem2._deterministic_intents(value, target))
    except Exception:
        pass
    for child in value.values():
        if isinstance(child, (dict, list)):
            intents |= _action_intents(child, target)
    return intents


def _feedback_class(trigger_intents, action_intents):
    if trigger_intents and action_intents and action_intents <= trigger_intents:
        return "state_reassertion_feedback", "low"
    if trigger_intents and action_intents and any(x not in trigger_intents for x in action_intents):
        return "state_transition_feedback", "medium"
    if action_intents:
        return "controlled_entity_feedback", "medium"
    return "feedback_loop_review", "medium"


def build_feedback_semantics(report, automation_map=None):
    automation_map, parse_errors = (automation_map, []) if automation_map is not None else effective_automation_map(report)
    graph = [x for x in report.get("dependency_graph") or [] if isinstance(x, dict)]
    items = []
    for node in graph:
        alias = str(node.get("automation") or "")
        shared = sorted(set(str(x) for x in node.get("triggers_on") or []) & set(str(x) for x in node.get("controls") or []))
        if not shared:
            continue
        records = (automation_map or {}).get(alias) or []
        effective = records[0].get("effective") or {} if len(records) == 1 else {}
        actions = effective.get("actions", effective.get("action", [])) if isinstance(effective, dict) else []
        for target in shared:
            trigger_intents = _trigger_state_intents(effective, target)
            action_intents = _action_intents(actions, target)
            classification, risk = _feedback_class(trigger_intents, action_intents)
            items.append({
                "automation": alias, "entity_id": target, "classification": classification,
                "risk": risk, "trigger_state_intents": sorted(trigger_intents),
                "action_state_intents": sorted(action_intents), "runtime_loop_proven": False,
                "manual_review_required": classification != "state_reassertion_feedback",
            })
    result = {
        "model": LOOP_MODEL, "count": len(items), "items": items[:30],
        "state_reassertion_count": sum(1 for x in items if x.get("classification") == "state_reassertion_feedback"),
        "state_transition_count": sum(1 for x in items if x.get("classification") == "state_transition_feedback"),
        "review_count": sum(1 for x in items if x.get("manual_review_required")),
        "parse_error_count": len(parse_errors or []), "runtime_loop_proven_count": 0,
    }
    report["automation_feedback_semantics"] = result
    return result


def apply_automation_precision(report):
    amap, parse_errors = effective_automation_map(report)
    duplicate = build_duplicate_semantics(report, amap)
    feedback = build_feedback_semantics(report, amap)
    report["automation_precision"] = {
        "model": "automation_precision_v1", "duplicate_model": DUPLICATE_MODEL,
        "feedback_model": LOOP_MODEL, "parse_error_count": len(parse_errors or []),
        "exact_duplicate_count": duplicate.get("count", 0), "feedback_relation_count": feedback.get("count", 0),
        "automatic_fix": False, "read_only": True,
    }
    return report["automation_precision"]
