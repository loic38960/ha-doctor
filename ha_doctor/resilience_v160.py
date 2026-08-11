"""HA Doctor 0.16 phase-aware resilience precision.

A sensor mentioned by an automation is not automatically a pre-control SPOF.
V5 keeps the validated role-aware V4 analysis, then inspects where the entity
is consumed relative to physical commands: trigger/gate, pre-action decision,
post-action confirmation, mixed feedback, or unresolved. No template is
executed and no Home Assistant state is read.
"""

import json
from resilience_v100 import build_resilience_recommendations_v3
from semantics_v081 import effective_automation_map
from contracts_v160 import RESILIENCE_MODEL, RESILIENCE_RECOMMENDATION_MODEL

_PHYSICAL_DOMAINS = {
    "alarm_control_panel", "button", "climate", "cover", "fan", "lawn_mower",
    "light", "lock", "media_player", "number", "remote", "select", "siren",
    "switch", "vacuum", "valve", "water_heater",
}


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _service(node):
    if not isinstance(node, dict):
        return ""
    raw = node.get("service")
    if isinstance(raw, str):
        return raw
    raw = node.get("action")
    return raw if isinstance(raw, str) and "." in raw else ""


def _physical_action(node):
    service = _service(node)
    return service.split(".", 1)[0] in _PHYSICAL_DOMAINS if "." in service else False


def _contains_entity(value, entity_id):
    if isinstance(value, str):
        return entity_id in value
    if isinstance(value, list):
        return any(_contains_entity(x, entity_id) for x in value)
    if isinstance(value, dict):
        return any(_contains_entity(v, entity_id) for v in value.values())
    return False


def _trigger_phase(effective, entity_id):
    triggers = effective.get("triggers", effective.get("trigger", [])) if isinstance(effective, dict) else []
    kinds = []
    for trigger in _as_list(triggers):
        if not isinstance(trigger, dict) or not _contains_entity(trigger.get("entity_id"), entity_id):
            continue
        platform = str(trigger.get("platform") or trigger.get("trigger") or "")
        kinds.append(platform or "unknown")
    return kinds


def _action_phase(effective, entity_id):
    pre = post = physical = 0

    def walk(sequence, seen_physical=False):
        nonlocal pre, post, physical
        local_seen = seen_physical
        for action in _as_list(sequence):
            if not isinstance(action, dict):
                continue
            # Conditions/branch selectors are evaluated before their branch action.
            if "choose" in action:
                for choice in _as_list(action.get("choose")):
                    if not isinstance(choice, dict):
                        continue
                    if _contains_entity(choice.get("conditions", choice.get("condition", [])), entity_id):
                        pre += 1 if not local_seen else 0; post += 1 if local_seen else 0
                    walk(choice.get("sequence", []), local_seen)
                if action.get("default") is not None:
                    walk(action.get("default"), local_seen)
                continue
            if "if" in action:
                if _contains_entity(action.get("if"), entity_id):
                    pre += 1 if not local_seen else 0; post += 1 if local_seen else 0
                walk(action.get("then", []), local_seen)
                if action.get("else") is not None:
                    walk(action.get("else", []), local_seen)
                continue
            if "sequence" in action and not _service(action):
                walk(action.get("sequence", []), local_seen)
                continue

            references = _contains_entity(action, entity_id)
            is_physical = _physical_action(action)
            if references:
                if local_seen:
                    post += 1
                else:
                    pre += 1
            if is_physical:
                physical += 1
                local_seen = True

    if not isinstance(effective, dict):
        return {"pre": 0, "post": 0, "physical": 0}
    # Top-level conditions and variables influence the decision before actions.
    if _contains_entity(effective.get("conditions", effective.get("condition", [])), entity_id):
        pre += 1
    if _contains_entity(effective.get("variables", {}), entity_id):
        pre += 1
    walk(effective.get("actions", effective.get("action", [])), False)
    return {"pre": pre, "post": post, "physical": physical}


def classify_dependency_phase(effective, entity_id):
    triggers = _trigger_phase(effective, entity_id)
    actions = _action_phase(effective, entity_id)
    if triggers and actions["pre"] == 0 and actions["post"] == 0:
        phase = "pre_control_trigger"
    elif actions["pre"] > 0 and actions["post"] == 0:
        phase = "pre_control_decision"
    elif actions["post"] > 0 and actions["pre"] == 0:
        phase = "post_action_confirmation"
    elif actions["pre"] > 0 and actions["post"] > 0:
        phase = "mixed_feedback_control"
    elif triggers and actions["post"] > 0:
        phase = "trigger_plus_post_confirmation"
    else:
        phase = "unresolved_reference_phase"
    return {
        "phase": phase,
        "trigger_platforms": sorted(set(triggers)),
        "pre_action_reference_count": actions["pre"],
        "post_action_reference_count": actions["post"],
        "physical_command_count": actions["physical"],
        "static_only": True,
        "templates_executed": False,
    }


def refine_resilience_v5(report):
    base_result = build_resilience_recommendations_v3(report)
    amap, parse_errors = effective_automation_map(report)
    analysis = report.get("resilience_analysis") or {}
    phase_by_entity = {}

    for dep in analysis.get("items") or []:
        if not isinstance(dep, dict) or not dep.get("entity_id"):
            continue
        entity_id = str(dep.get("entity_id"))
        evidence = []
        for ev in dep.get("automation_evidence") or []:
            if not isinstance(ev, dict) or not ev.get("automation"):
                continue
            alias = str(ev.get("automation"))
            records = amap.get(alias) or []
            phase = {"phase": "unresolved_reference_phase", "static_only": True, "templates_executed": False}
            if len(records) == 1:
                phase = classify_dependency_phase(records[0].get("effective") or {}, entity_id)
            phase.update({
                "automation": alias,
                "protection": ev.get("protection"),
                "risk_relevant": bool(ev.get("risk_relevant")),
                "role": ev.get("role"),
            })
            evidence.append(phase)
        phase_by_entity[entity_id] = evidence
        dep["phase_evidence"] = evidence[:30]
        dep["pre_control_risk_count"] = sum(1 for x in evidence if x.get("risk_relevant") and x.get("phase") in {"pre_control_decision", "mixed_feedback_control", "unresolved_reference_phase"} and x.get("protection") in {"none", "weak"})
        dep["post_action_only_risk_count"] = sum(1 for x in evidence if x.get("risk_relevant") and x.get("phase") in {"post_action_confirmation", "trigger_plus_post_confirmation"} and x.get("protection") in {"none", "weak"})

    recs = report.get("resilience_recommendations") or base_result or {}
    refined = []
    for rec in recs.get("items") or []:
        if not isinstance(rec, dict):
            continue
        row = dict(rec)
        entity_id = str(row.get("entity_id") or "")
        phases = phase_by_entity.get(entity_id, [])
        risky_names = set(str(x) for x in row.get("risky_automations") or [])
        relevant = [x for x in phases if x.get("automation") in risky_names] if risky_names else phases
        pre_risk = [x for x in relevant if x.get("phase") in {"pre_control_decision", "mixed_feedback_control", "unresolved_reference_phase"}]
        post_only = [x for x in relevant if x.get("phase") in {"post_action_confirmation", "trigger_plus_post_confirmation"}]
        trigger_only = [x for x in relevant if x.get("phase") == "pre_control_trigger"]
        row["phase_evidence"] = relevant[:12]
        row["pre_control_risk_count"] = len(pre_risk)
        row["post_action_confirmation_count"] = len(post_only)
        row["trigger_dependency_count"] = len(trigger_only)
        if row.get("tier") == "must_fix" and relevant and not pre_risk and (post_only or trigger_only):
            row["tier"] = "hardening"
            row["phase_adjustment"] = "no_unprotected_pre_control_decision_proven"
        elif pre_risk:
            row["phase_adjustment"] = "pre_control_dependency_confirmed_or_unresolved"
        else:
            row["phase_adjustment"] = "no_phase_change"
        refined.append(row)

    must_fix = sum(1 for x in refined if x.get("tier") == "must_fix")
    hardening = sum(1 for x in refined if x.get("tier") == "hardening")
    result = {
        "model": RESILIENCE_RECOMMENDATION_MODEL,
        "analysis_model": RESILIENCE_MODEL,
        "count": len(refined), "must_fix_count": must_fix, "hardening_count": hardening,
        "items": refined,
        "selection_policy": "pre_control_exposure_before_post_action_confirmation",
        "phase_parse_error_count": len(parse_errors or []),
        "scoring_applied": False,
        "note": "La phase statique d'utilisation affine la priorité sans modifier rétroactivement le score technique.",
    }
    report["resilience_recommendations"] = result
    report["resilience_precision"] = {
        "model": RESILIENCE_MODEL,
        "dependencies_analyzed": len(phase_by_entity),
        "phase_evidence_count": sum(len(x) for x in phase_by_entity.values()),
        "parse_error_count": len(parse_errors or []),
        "templates_executed": False,
    }
    return result
