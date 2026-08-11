"""HA Doctor 0.15 execution board.

Decision V3 keeps the 0.14 operational lanes, but makes the remaining controller
review event-aware and exposes one compact operational summary that can be used
consistently by UI, support export and executive text.
"""

import decision_v140 as base
from contracts_v150 import DECISION_MODEL, ENTITY_ATTENTION_MODEL, REPAIR_PLAYBOOK_MODEL


def _event_overlap(report):
    sem = report.get("condition_semantics") or {}
    items = []
    for pair in sem.get("unproven_pairs") or []:
        if not isinstance(pair, dict):
            continue
        event = pair.get("v10_event_analysis") or {}
        if event.get("status") != "event_window_policy_overlap":
            continue
        items.append({
            "entity_id": pair.get("entity_id"),
            "automations": list(pair.get("automations") or [])[:2],
            "review_priority": pair.get("review_priority"),
            "event_analysis": event,
        })
    return items


def _upgrade_playbook(item, report):
    pb = dict(item.get("repair_playbook") or {})
    pb["model"] = REPAIR_PLAYBOOK_MODEL
    if str(item.get("source_id") or "") == "HD-AUTO-003":
        overlaps = _event_overlap(report)
        if overlaps:
            first = overlaps[0]
            event = first.get("event_analysis") or {}
            windows = []
            for conflict in event.get("conflicts") or []:
                windows.extend(conflict.get("overlap_evidence") or [])
            pb.update({
                "category": "controller_event_window_policy",
                "repair_readiness": "needs_logic_review",
                "event_window_policy": {
                    "entity_id": first.get("entity_id"),
                    "automations": first.get("automations") or [],
                    "windows": windows[:6],
                    "event_kinds": event.get("event_kinds") or [],
                    "crossing_event_conflict_count": event.get("crossing_event_conflict_count", 0),
                    "simultaneous_execution_proven": False,
                    "continuous_conflict_proven": False,
                },
                "steps": [
                    {"step": 1, "detail": "Vérifier l'intention dans la fenêtre signalée en distinguant le franchissement numeric_state d'un état qui resterait continuellement vrai."},
                    {"step": 2, "detail": "Décider si l'arrêt au franchissement puis une éventuelle reprise ultérieure est volontaire, ou si un seul contrôleur doit posséder cette zone."},
                    {"step": 3, "detail": "Si la politique n'est pas volontaire, rendre l'arbitrage explicite avec priorité, hystérésis ou seuils disjoints puis rescanner."},
                ],
                "success_criteria": [
                    "La fenêtre de politique est explicitement arbitrée ou documentée comme un handoff événementiel voulu.",
                    "HA Doctor ne présente plus un overlap ambigu comme un conflit continu potentiel.",
                ],
            })
    pb["automatic_fix"] = False
    pb["read_only"] = True
    return pb


def build_decision_engine_v3(report):
    result = base.build_decision_engine_v2(report)
    decisions = []
    for item in result.get("items") or []:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        item["repair_playbook"] = _upgrade_playbook(item, report)
        decisions.append(item)

    # Keep the same deterministic ordering from V2.
    result["items"] = decisions
    result["model"] = DECISION_MODEL
    result["event_window_policy"] = _event_overlap(report)
    result["event_window_policy_count"] = len(result["event_window_policy"])
    result["top"] = [x for x in decisions if x.get("operational_lane") != "watch"][:8]
    result["policy"] = "root_cause_then_operational_lane_then_event_aware_evidence_then_priority"

    attention = dict(result.get("entity_attention") or {})
    attention["model"] = ENTITY_ATTENTION_MODEL
    attention["primary_decision_count"] = len([x for x in decisions if x.get("operational_lane") != "watch"])
    attention["watch_decision_count"] = len([x for x in decisions if x.get("operational_lane") == "watch"])
    result["entity_attention"] = attention

    summary = {
        "model": "operational_summary_v1",
        "fix_now": int((result.get("lane_counts") or {}).get("fix_now", 0)),
        "logic_review": int((result.get("lane_counts") or {}).get("logic_review", 0)),
        "restore_if_needed": int((result.get("lane_counts") or {}).get("restore_if_needed", 0)),
        "watch": int((result.get("lane_counts") or {}).get("watch", 0)),
        "optimize": int((result.get("lane_counts") or {}).get("optimize", 0)),
        "primary_action_count": int(result.get("primary_action_count", 0)),
        "event_window_policy_count": int(result.get("event_window_policy_count", 0)),
    }
    result["operational_summary"] = summary
    report["decision_engine"] = result
    report["operational_summary"] = summary
    report.setdefault("product_intelligence", {})["entity_attention"] = attention

    # Synchronize action-plan embedded playbooks/models as well.
    by_id = {str(x.get("id")): x for x in decisions if x.get("id")}
    for action in (report.get("action_plan") or {}).get("items") or []:
        if isinstance(action, dict) and str(action.get("id")) in by_id:
            src = by_id[str(action.get("id"))]
            action["repair_playbook"] = src.get("repair_playbook") or {}
            action["operational_lane"] = src.get("operational_lane")
            action["operational_relevance"] = src.get("operational_relevance")
            action["execution_priority_score"] = src.get("execution_priority_score")
    return result
