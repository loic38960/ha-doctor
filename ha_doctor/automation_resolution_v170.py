"""HA Doctor 0.17 automation resolution intelligence.

Refines exact duplicate actions and self-feedback relationships without claiming
runtime behavior that static YAML cannot prove. The main new proof is the
terminating state transition: a specific `to:` state trigger followed by a
command to the opposite state does not immediately satisfy the same trigger
again and is therefore not, by itself, a static self-loop.
"""

from automation_precision_v160 import apply_automation_precision as apply_v160
from automation_precision_v160 import _action_intents, _trigger_state_intents
from semantics_v081 import effective_automation_map
import semantics_v082 as sem2
from contracts_v170 import FEEDBACK_MODEL, DUPLICATE_MODEL


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _trigger_profile(effective, target):
    profiles = []
    for trigger in sem2._trigger_list(effective):
        if not isinstance(trigger, dict):
            continue
        ids = {str(x) for x in sem2._entity_ids(trigger.get("entity_id"))}
        if target not in ids:
            continue
        platform = str(trigger.get("platform") or trigger.get("trigger") or "").lower()
        to = trigger.get("to")
        frm = trigger.get("from")
        profiles.append({
            "platform": platform,
            "to": str(to).lower() if isinstance(to, str) else None,
            "from": str(frm).lower() if isinstance(frm, str) else None,
            "specific_state_edge": platform == "state" and isinstance(to, str),
        })
    return profiles


def _classify_feedback(profile, trigger_intents, action_intents):
    state_profiles = [x for x in profile if x.get("platform") == "state"]
    specific_to = {f"state:{x['to']}" for x in state_profiles if x.get("specific_state_edge") and x.get("to") in {"on", "off"}}
    broad_state = any(x.get("platform") == "state" and not x.get("specific_state_edge") for x in profile)

    if trigger_intents and action_intents and action_intents <= trigger_intents:
        return "state_reassertion_feedback", "low", False, "same_state_reassertion"

    # Example: trigger `to: on`, action `turn_off`. The action moves away from
    # the edge that caused the run. A new run needs a future re-entry to `on`.
    if specific_to and action_intents and action_intents.isdisjoint(specific_to) and not broad_state:
        return "terminating_state_transition", "low", False, "specific_edge_requires_future_reentry"

    if broad_state and action_intents:
        return "self_retrigger_candidate", "high", True, "broad_state_trigger_can_observe_own_transition"

    if specific_to and action_intents and not action_intents.isdisjoint(specific_to):
        return "trigger_state_reentry_candidate", "medium", True, "action_can_restore_trigger_to_state"

    if action_intents:
        return "controlled_entity_feedback", "medium", True, "insufficient_static_trigger_intent"
    return "feedback_loop_review", "medium", True, "no_deterministic_action_intent"


def build_feedback_v2(report, automation_map=None):
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
            profile = _trigger_profile(effective, target)
            classification, risk, review, reason = _classify_feedback(profile, trigger_intents, action_intents)
            items.append({
                "automation": alias, "entity_id": target, "classification": classification,
                "risk": risk, "reason": reason, "trigger_profile": profile[:6],
                "trigger_state_intents": sorted(trigger_intents), "action_state_intents": sorted(action_intents),
                "static_self_loop_proven": False, "runtime_loop_proven": False,
                "manual_review_required": bool(review),
            })
    result = {
        "model": FEEDBACK_MODEL, "count": len(items), "items": items[:30],
        "state_reassertion_count": sum(1 for x in items if x.get("classification") == "state_reassertion_feedback"),
        "terminating_transition_count": sum(1 for x in items if x.get("classification") == "terminating_state_transition"),
        "self_retrigger_candidate_count": sum(1 for x in items if x.get("classification") == "self_retrigger_candidate"),
        "reentry_candidate_count": sum(1 for x in items if x.get("classification") == "trigger_state_reentry_candidate"),
        "review_count": sum(1 for x in items if x.get("manual_review_required")),
        "statically_resolved_count": sum(1 for x in items if not x.get("manual_review_required")),
        "parse_error_count": len(parse_errors or []), "runtime_loop_proven_count": 0,
    }
    report["automation_feedback_semantics"] = result
    return result


def build_duplicate_v2(report):
    base = report.get("duplicate_action_semantics") or {}
    items = []
    for raw in base.get("items") or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        kind = str(row.get("classification") or "")
        row["resolution_status"] = "manual_fix_ready" if kind == "side_effect_duplicate" and row.get("exact_duplicate") is True else "logic_review_required"
        row["repair_confidence"] = "high" if row["resolution_status"] == "manual_fix_ready" else "medium"
        row["automatic_removal_safe"] = False
        items.append(row)
    result = {
        **base, "model": DUPLICATE_MODEL, "items": items[:30],
        "manual_fix_ready_count": sum(1 for x in items if x.get("resolution_status") == "manual_fix_ready"),
        "automatic_cleanup": False,
    }
    report["duplicate_action_semantics"] = result
    return result


def apply_automation_resolution(report):
    apply_v160(report)
    amap, parse_errors = effective_automation_map(report)
    feedback = build_feedback_v2(report, amap)
    duplicate = build_duplicate_v2(report)
    result = {
        "model": "automation_resolution_v2", "feedback_model": FEEDBACK_MODEL,
        "duplicate_model": DUPLICATE_MODEL, "feedback_count": feedback.get("count", 0),
        "feedback_statically_resolved_count": feedback.get("statically_resolved_count", 0),
        "duplicate_manual_fix_ready_count": duplicate.get("manual_fix_ready_count", 0),
        "parse_error_count": len(parse_errors or []), "runtime_execution_observed": False,
        "automatic_fix": False, "read_only": True,
    }
    report["automation_resolution"] = result
    return result
