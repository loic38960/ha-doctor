"""HA Doctor 0.16 precision Decision Engine.

Decision V4 consumes exact unresolved-controller impact, phase-aware resilience,
automation feedback semantics and duplicate-action semantics. One canonical
ordering is then reused by the action plan, Doctor View and support export.
"""

from collections import Counter
from decision_v150 import build_decision_engine_v3
from contracts_v160 import (
    DECISION_MODEL, CANONICAL_ORDER_MODEL, ENTITY_ATTENTION_MODEL,
    REPAIR_PLAYBOOK_MODEL, CONTROLLER_IMPACT_MODEL,
)

_LANE_RANK = {"fix_now": 0, "logic_review": 1, "restore_if_needed": 2, "optimize": 3, "watch": 4}
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_RELEVANCE_RANK = {"high": 0, "medium": 1, "low": 2}


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def _float(value, default=0.0):
    try:
        return float(value if value is not None else default)
    except Exception:
        return float(default)


def _precision_score(item):
    lane = str(item.get("operational_lane") or "watch")
    relevance = str(item.get("operational_relevance") or "low")
    severity = str(item.get("severity") or "low")
    confidence = _float(item.get("confidence_score"), 0.5)
    dep = item.get("dependency_impact") or {}
    impacted = _int(dep.get("impacted_automation_count"), 0)
    level = str(dep.get("level") or "none")
    score = {
        "fix_now": 65, "logic_review": 46, "restore_if_needed": 35, "optimize": 20, "watch": 8,
    }.get(lane, 10)
    score += {"high": 18, "medium": 9, "low": 2}.get(relevance, 0)
    score += {"critical": 12, "high": 9, "medium": 6, "low": 2, "info": 0}.get(severity, 0)
    score += round(confidence * 6)
    score += min(8, impacted)
    score += {"critical": 8, "high": 6, "medium": 3, "low": 1, "none": 0}.get(level, 0)
    return min(100, score)


def canonical_order_key(item):
    return (
        _LANE_RANK.get(str(item.get("operational_lane") or "watch"), 9),
        _RELEVANCE_RANK.get(str(item.get("operational_relevance") or "low"), 9),
        -_int(item.get("execution_priority_score"), 0),
        _SEVERITY_RANK.get(str(item.get("severity") or "low"), 9),
        -_float(item.get("confidence_score"), 0.0),
        str(item.get("id") or ""),
    )


def _replace_controller_impact(item, report):
    if str(item.get("source_id") or "") != "HD-AUTO-003":
        return
    impact = report.get("controller_impact") or (report.get("condition_semantics") or {}).get("controller_impact") or {}
    if not impact:
        return
    previous = dict(item.get("dependency_impact") or {})
    item["historical_dependency_impact"] = previous
    item["dependency_impact"] = {
        "model": CONTROLLER_IMPACT_MODEL,
        "level": impact.get("level", "none"),
        "impacted_automation_count": _int(impact.get("impacted_automation_count"), 0),
        "impacted_automations": list(impact.get("impacted_automations") or []),
        "target_entities": list(impact.get("target_entities") or []),
        "physical_pair_count": _int(impact.get("physical_pair_count"), 0),
        "weighted_impact_score": _float(impact.get("weighted_impact_score"), 0.0),
        "scope": "unresolved_physical_pairs_only",
        "broad_historical_blast_radius_not_used_for_priority": True,
    }


def _upgrade_duplicate(item, report):
    if str(item.get("source_id") or "") != "HD-AUTO-005":
        return
    dup = report.get("duplicate_action_semantics") or {}
    pb = dict(item.get("repair_playbook") or {})
    pb["model"] = REPAIR_PLAYBOOK_MODEL
    if _int(dup.get("side_effect_duplicate_count"), 0) > 0:
        pb["category"] = "duplicate_side_effect"
        pb["repair_readiness"] = "ready_for_manual_change"
        pb["steps"] = [
            {"step": 1, "detail": "Ouvrir l'automatisation signalée et confirmer que les deux actions consécutives sont strictement identiques."},
            {"step": 2, "detail": "Vérifier que la répétition n'est pas volontaire, notamment pour les notifications ou autres effets externes."},
            {"step": 3, "detail": "Si elle est involontaire, supprimer manuellement une seule occurrence puis rescanner."},
        ]
        pb["success_criteria"] = ["HA Doctor ne détecte plus l'action consécutive identique."]
    pb["automatic_fix"] = False; pb["read_only"] = True
    item["repair_playbook"] = pb
    item["duplicate_semantics"] = {k: dup.get(k) for k in ("count", "side_effect_duplicate_count", "idempotent_control_candidate_count", "repeated_script_call_count")}


def _upgrade_feedback(item, report):
    if str(item.get("source_id") or "") != "HD-AUTO-008":
        return
    feedback = report.get("automation_feedback_semantics") or {}
    item["feedback_semantics"] = {k: feedback.get(k) for k in ("count", "state_reassertion_count", "state_transition_count", "review_count", "runtime_loop_proven_count")}
    if _int(feedback.get("count"), 0) and _int(feedback.get("review_count"), 0) == 0:
        item["operational_relevance"] = "low"
        pb = dict(item.get("repair_playbook") or {})
        pb["model"] = REPAIR_PLAYBOOK_MODEL
        pb["category"] = "state_reassertion_feedback"
        pb["repair_readiness"] = "observe_only"
        pb["steps"] = [{"step": 1, "detail": "Vérifier que la réaffirmation du même état est volontaire ; aucune boucle runtime n'est prouvée statiquement."}]
        pb["success_criteria"] = ["La réaffirmation est documentée ou simplifiée manuellement si elle est inutile."]
        pb["automatic_fix"] = False; pb["read_only"] = True
        item["repair_playbook"] = pb


def _upgrade_resilience(item, report):
    if str(item.get("source_id") or "") != "HD-RES-001":
        return
    recs = report.get("resilience_recommendations") or {}
    risky = sorted({str(name) for rec in recs.get("items") or [] if isinstance(rec, dict) for name in rec.get("risky_automations") or []})
    pre = sum(_int((rec or {}).get("pre_control_risk_count"), 0) for rec in recs.get("items") or [] if isinstance(rec, dict))
    post = sum(_int((rec or {}).get("post_action_confirmation_count"), 0) for rec in recs.get("items") or [] if isinstance(rec, dict))
    item["resilience_phase_precision"] = {
        "model": recs.get("model"), "must_fix_count": recs.get("must_fix_count", 0),
        "hardening_count": recs.get("hardening_count", 0), "pre_control_risk_count": pre,
        "post_action_confirmation_count": post, "risky_automations": risky,
    }
    dep = dict(item.get("dependency_impact") or {})
    dep["impacted_automation_count"] = len(risky)
    dep["impacted_automations"] = risky
    dep["phase_aware"] = True
    item["dependency_impact"] = dep


def _sync_action_plan(report, decisions):
    by_id = {str(x.get("id")): x for x in decisions if x.get("id")}
    actions = []
    for raw in (report.get("action_plan") or {}).get("items") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        source = by_id.get(str(item.get("id")))
        if source:
            for key in (
                "operational_lane", "operational_relevance", "execution_priority_score",
                "repair_playbook", "dependency_impact", "historical_dependency_impact",
                "duplicate_semantics", "feedback_semantics", "resilience_phase_precision",
            ):
                if key in source:
                    item[key] = source[key]
        actions.append(item)
    actions.sort(key=canonical_order_key)
    report.setdefault("action_plan", {})["items"] = actions
    report["action_plan"]["total"] = len(actions)
    return actions


def build_decision_engine_v4(report):
    base = build_decision_engine_v3(report)
    decisions = []
    for raw in base.get("items") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        _replace_controller_impact(item, report)
        _upgrade_duplicate(item, report)
        _upgrade_feedback(item, report)
        _upgrade_resilience(item, report)
        item["execution_priority_score"] = _precision_score(item)
        decisions.append(item)
    decisions.sort(key=canonical_order_key)

    actions = _sync_action_plan(report, decisions)
    lane_counts = Counter(str(x.get("operational_lane") or "watch") for x in decisions)
    readiness = Counter(str((x.get("repair_playbook") or {}).get("repair_readiness") or "unknown") for x in decisions)
    relevance = Counter(str(x.get("operational_relevance") or "low") for x in decisions)
    primary = [x for x in decisions if x.get("operational_lane") != "watch"]
    result = {
        **base,
        "model": DECISION_MODEL, "items": decisions, "total": len(decisions),
        "top": primary[:10], "primary_action_count": len(primary),
        "lane_counts": dict(lane_counts), "repair_readiness_counts": dict(readiness),
        "operational_relevance_counts": dict(relevance),
        "canonical_order": {
            "model": CANONICAL_ORDER_MODEL,
            "item_ids": [str(x.get("id")) for x in decisions],
            "primary_item_ids": [str(x.get("id")) for x in primary],
            "policy": "lane_then_relevance_then_precision_score_then_severity_then_confidence",
        },
        "controller_impact": report.get("controller_impact") or {},
        "duplicate_action_semantics": report.get("duplicate_action_semantics") or {},
        "automation_feedback_semantics": report.get("automation_feedback_semantics") or {},
        "policy": "precision_evidence_then_single_canonical_order",
        "automatic_fix": False, "read_only": True,
    }
    attention = dict(result.get("entity_attention") or {})
    attention["model"] = ENTITY_ATTENTION_MODEL
    attention["primary_decision_count"] = len(primary)
    attention["watch_decision_count"] = len(decisions) - len(primary)
    attention["controller_physical_automation_count"] = _int((report.get("controller_impact") or {}).get("impacted_automation_count"), 0)
    result["entity_attention"] = attention

    report["decision_engine"] = result
    report["canonical_decision_order"] = result["canonical_order"]
    report.setdefault("action_plan", {})["model"] = report.get("action_plan", {}).get("model")
    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["plan_id_count"] = len(actions)
    diagnostic["top_actions"] = [
        {k: x.get(k) for k in ("id", "title", "severity", "domain", "confidence", "operational_lane", "operational_relevance")}
        for x in decisions[:5]
    ]
    return result
