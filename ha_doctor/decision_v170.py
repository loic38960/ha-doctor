"""HA Doctor 0.17 Resolution Decision Engine.

Consumes V4 precision decisions then resolves what static evidence can honestly
resolve. It never changes Home Assistant. Exact duplicate side effects can be
promoted to a manual fix, terminating self-feedback can be demoted from review,
and missing references can be watched when no runtime impact is demonstrated.
"""

from collections import Counter
from decision_v160 import build_decision_engine_v4
from decision_v160 import canonical_order_key as _legacy_order_key
from contracts_v170 import (
    DECISION_MODEL, CANONICAL_ORDER_MODEL, REPAIR_PLAYBOOK_MODEL,
    ACTION_PLAN_MODEL, RESOLUTION_MODEL,
)

_LANE_RANK = {"fix_now": 0, "logic_review": 1, "restore_if_needed": 2, "optimize": 3, "watch": 4}
_RELEVANCE_RANK = {"high": 0, "medium": 1, "low": 2}
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


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


def canonical_order_key(item):
    return (
        _LANE_RANK.get(str(item.get("operational_lane") or "watch"), 9),
        _RELEVANCE_RANK.get(str(item.get("operational_relevance") or "low"), 9),
        -_int(item.get("execution_priority_score"), 0),
        _SEVERITY_RANK.get(str(item.get("severity") or "low"), 9),
        -_float(item.get("confidence_score"), 0.0),
        str(item.get("id") or ""),
    )


def _playbook(item):
    pb = dict(item.get("repair_playbook") or {})
    pb["model"] = REPAIR_PLAYBOOK_MODEL
    pb["automatic_fix"] = False
    pb["read_only"] = True
    pb.setdefault("steps", [{"step": 1, "detail": "Vérifier manuellement le diagnostic et son intention avant toute modification."}])
    pb.setdefault("success_criteria", ["Le diagnostic disparaît après une correction volontaire et un nouveau scan."])
    return pb


def _source_domain_map(report):
    by_id = {}
    for item in (report.get("action_plan") or {}).get("items") or []:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item.get("id"))] = item.get("domain")
    finding_domains = {
        str(x.get("rule_id")): x.get("domain")
        for x in report.get("findings") or [] if isinstance(x, dict) and x.get("rule_id")
    }
    return by_id, finding_domains


def _duplicate_resolution(item, report):
    if str(item.get("source_id") or "") != "HD-AUTO-005":
        return False
    duplicate = report.get("duplicate_action_semantics") or {}
    ready = _int(duplicate.get("manual_fix_ready_count"), 0)
    if ready <= 0:
        return False
    item["operational_lane"] = "fix_now"
    item["operational_relevance"] = "medium"
    item["resolution_status"] = "manual_fix_ready"
    item["resolution_evidence"] = {
        "model": duplicate.get("model"), "manual_fix_ready_count": ready,
        "side_effect_duplicate_count": duplicate.get("side_effect_duplicate_count", 0),
        "automatic_removal_safe": False,
    }
    pb = _playbook(item)
    pb.update({
        "category": "exact_duplicate_side_effect",
        "repair_readiness": "ready_for_manual_change",
        "steps": [
            {"step": 1, "detail": "Ouvrir l'automatisation signalée et confirmer les deux actions consécutives strictement identiques."},
            {"step": 2, "detail": "Confirmer que la répétition n'est pas une redondance volontaire destinée à un service externe."},
            {"step": 3, "detail": "Supprimer manuellement une seule occurrence si la répétition est involontaire, puis rescanner."},
        ],
        "success_criteria": ["Le doublon consécutif exact n'est plus détecté.", "Le comportement attendu de l'automatisation reste inchangé hors répétition."],
    })
    item["repair_playbook"] = pb
    return True


def _feedback_resolution(item, report):
    if str(item.get("source_id") or "") != "HD-AUTO-008":
        return False
    feedback = report.get("automation_feedback_semantics") or {}
    count = _int(feedback.get("count"), 0)
    review = _int(feedback.get("review_count"), count)
    resolved = _int(feedback.get("statically_resolved_count"), 0)
    item["feedback_resolution"] = {
        "model": feedback.get("model"), "count": count, "review_count": review,
        "statically_resolved_count": resolved,
        "terminating_transition_count": feedback.get("terminating_transition_count", 0),
        "runtime_loop_proven_count": 0,
    }
    if count > 0 and review == 0:
        item["operational_lane"] = "watch"
        item["operational_relevance"] = "low"
        item["resolution_status"] = "statically_resolved"
        pb = _playbook(item)
        pb.update({
            "category": "resolved_static_feedback",
            "repair_readiness": "resolved_static",
            "steps": [{"step": 1, "detail": "Aucune correction n'est imposée : surveiller uniquement si le comportement runtime observé est anormal."}],
            "success_criteria": ["Aucune boucle runtime n'est observée ; la transition statique reste cohérente avec le trigger."],
        })
        item["repair_playbook"] = pb
        return True
    item["resolution_status"] = "logic_review_required"
    return False


def _reference_resolution(item, report):
    if str(item.get("source_id") or "") != "HD-CFG-001":
        return False
    refs = report.get("missing_reference_intelligence") or {}
    runtime = _int(refs.get("runtime_relevant_count"), 0)
    item["missing_reference_resolution"] = {
        "model": refs.get("model"), "runtime_relevant_count": runtime,
        "low_impact_count": refs.get("low_impact_count", 0),
        "archive_or_inactive_count": refs.get("archive_or_inactive_count", 0),
        "replacement_inference_enabled": False,
    }
    if refs.get("finding_present") and runtime == 0 and refs.get("evidence_entity_count", 0) > 0:
        item["operational_lane"] = "watch"
        item["operational_relevance"] = "low"
        item["resolution_status"] = "watch_only"
        pb = _playbook(item)
        pb.update({
            "category": "missing_reference_low_operational_impact",
            "repair_readiness": "observe_only",
            "steps": [{"step": 1, "detail": "Revoir les références listées lors d'une maintenance YAML ; ne remplacer aucune entité sans preuve."}],
            "success_criteria": ["Chaque référence est soit restaurée, soit supprimée volontairement, soit documentée comme inactive."],
        })
        item["repair_playbook"] = pb
        return True
    item["resolution_status"] = "logic_review_required"
    return False


def _resilience_resolution(item, report):
    if str(item.get("source_id") or "") != "HD-RES-001":
        return
    recs = report.get("resilience_recommendations") or {}
    must = [x for x in recs.get("items") or [] if isinstance(x, dict) and x.get("tier") == "must_fix"]
    hardening = [x for x in recs.get("items") or [] if isinstance(x, dict) and x.get("tier") == "hardening"]
    item["resolution_status"] = "logic_review_required" if must else "optimization"
    item["resilience_resolution"] = {
        "model": recs.get("model"), "must_fix_count": len(must), "hardening_count": len(hardening),
        "guard_strategies": [x.get("guard_strategy") for x in (must + hardening) if x.get("guard_strategy")][:6],
    }
    pb = _playbook(item)
    if must:
        pb.update({
            "category": "external_dependency_guard",
            "repair_readiness": "needs_logic_review",
            "steps": [{"step": 1, "detail": "Ajouter manuellement une garde d'indisponibilité avant le contrôle physique concerné, après validation de l'intention métier."}],
            "success_criteria": ["Une mesure unavailable/unknown ne peut plus déclencher ou autoriser la commande physique dépendante."],
        })
    else:
        item["operational_lane"] = "optimize"
        item["operational_relevance"] = "low"
        pb["repair_readiness"] = "optimization"
    item["repair_playbook"] = pb


def _default_resolution(item):
    source_type = str(item.get("source_type") or "")
    lane = str(item.get("operational_lane") or "watch")
    if source_type.startswith("registry_") and lane == "watch":
        return "watch_only"
    if lane == "fix_now":
        return "manual_fix_ready"
    if lane == "logic_review":
        return "logic_review_required"
    if lane == "optimize":
        return "optimization"
    if lane == "restore_if_needed":
        return "external_restore_if_needed"
    return "watch_only"


def _score(item):
    # Keep 0.16 scoring stable but let the lane change drive ordering.
    lane = str(item.get("operational_lane") or "watch")
    relevance = str(item.get("operational_relevance") or "low")
    severity = str(item.get("severity") or "low")
    confidence = _float(item.get("confidence_score"), 0.5)
    dep = item.get("dependency_impact") or {}
    impacted = _int(dep.get("impacted_automation_count"), 0)
    base = {"fix_now": 65, "logic_review": 46, "restore_if_needed": 35, "optimize": 20, "watch": 8}.get(lane, 10)
    base += {"high": 18, "medium": 9, "low": 2}.get(relevance, 0)
    base += {"critical": 12, "high": 9, "medium": 6, "low": 2, "info": 0}.get(severity, 0)
    base += round(confidence * 6) + min(8, impacted)
    return min(100, base)


def _sync_action_plan(report, decisions):
    by_id = {str(x.get("id")): x for x in decisions if x.get("id")}
    actions = []
    for raw in (report.get("action_plan") or {}).get("items") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw); src = by_id.get(str(item.get("id")))
        if src:
            for key in (
                "domain", "operational_lane", "operational_relevance", "execution_priority_score",
                "repair_playbook", "dependency_impact", "resolution_status", "resolution_evidence",
                "feedback_resolution", "missing_reference_resolution", "resilience_resolution",
            ):
                if key in src: item[key] = src[key]
        actions.append(item)
    actions.sort(key=canonical_order_key)
    plan = report.setdefault("action_plan", {})
    plan["model"] = ACTION_PLAN_MODEL; plan["items"] = actions; plan["total"] = len(actions)
    return actions


def build_decision_engine_v5(report):
    original_domain, finding_domains = _source_domain_map(report)
    base = build_decision_engine_v4(report)
    decisions = []
    for raw in base.get("items") or []:
        if not isinstance(raw, dict): continue
        item = dict(raw)
        if not item.get("domain"):
            item["domain"] = original_domain.get(str(item.get("id"))) or finding_domains.get(str(item.get("source_id")))
        item["repair_playbook"] = _playbook(item)
        _duplicate_resolution(item, report)
        _feedback_resolution(item, report)
        _reference_resolution(item, report)
        _resilience_resolution(item, report)
        item.setdefault("resolution_status", _default_resolution(item))
        item["execution_priority_score"] = _score(item)
        decisions.append(item)
    decisions.sort(key=canonical_order_key)
    actions = _sync_action_plan(report, decisions)
    lanes = Counter(str(x.get("operational_lane") or "watch") for x in decisions)
    resolutions = Counter(str(x.get("resolution_status") or "logic_review_required") for x in decisions)
    primary = [x for x in decisions if x.get("operational_lane") != "watch"]
    result = {
        **base,
        "model": DECISION_MODEL, "items": decisions, "total": len(decisions), "top": primary[:10],
        "primary_action_count": len(primary), "lane_counts": dict(lanes),
        "resolution_counts": dict(resolutions),
        "canonical_order": {
            "model": CANONICAL_ORDER_MODEL, "item_ids": [str(x.get("id")) for x in decisions],
            "primary_item_ids": [str(x.get("id")) for x in primary],
            "policy": "resolution_lane_then_relevance_then_priority_score_then_severity_then_confidence",
        },
        "resolution_engine": {
            "model": RESOLUTION_MODEL,
            "manual_fix_ready_count": resolutions.get("manual_fix_ready", 0),
            "logic_review_required_count": resolutions.get("logic_review_required", 0),
            "statically_resolved_count": resolutions.get("statically_resolved", 0),
            "watch_only_count": resolutions.get("watch_only", 0),
        },
        "policy": "resolve_static_evidence_before_requesting_manual_review",
        "automatic_fix": False, "read_only": True,
    }
    report["decision_engine"] = result
    report["canonical_decision_order"] = result["canonical_order"]
    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["plan_id_count"] = len(actions)
    diagnostic["top_actions"] = [
        {k: x.get(k) for k in ("id", "title", "severity", "domain", "confidence", "operational_lane", "operational_relevance", "resolution_status")}
        for x in decisions[:5]
    ]
    return result
