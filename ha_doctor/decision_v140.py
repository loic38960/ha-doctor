"""HA Doctor 0.14 operational decision engine.

V2 keeps all diagnostics but separates immediate fixes, logic review, external
restoration, low-impact watch items and optimizations. Registry incidents with
zero automation impact no longer crowd the primary investigation lane.
"""

from collections import Counter
import decision_v130 as base
from contracts_v140 import DECISION_MODEL, ENTITY_ATTENTION_MODEL, REPAIR_PLAYBOOK_MODEL


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


def _impact(item):
    dep = item.get("dependency_impact") or {}
    return str(dep.get("level") or "none"), _int(dep.get("impacted_automation_count"), 0)


def _policy_overlap(report):
    sem = report.get("condition_semantics") or {}
    items = []
    for pair in sem.get("unproven_pairs") or []:
        if not isinstance(pair, dict):
            continue
        analysis = pair.get("v9_policy_analysis") or {}
        if analysis.get("status") != "policy_overlap":
            continue
        conflicts = analysis.get("conflicts") or []
        items.append({
            "entity_id": pair.get("entity_id"), "automations": pair.get("automations") or [],
            "conflict_path_pair_count": analysis.get("conflict_path_pair_count", len(conflicts)),
            "examples": conflicts[:3], "simultaneous_execution_proven": False,
        })
    return items


def _operational_lane(item):
    priority = str(item.get("priority") or "")
    source = str(item.get("source_type") or "")
    source_id = str(item.get("source_id") or "")
    level, impacted = _impact(item)
    if priority == "action_now":
        return "fix_now"
    if source_id in {"HD-AUTO-003", "HD-RES-001", "HD-AUTO-005", "HD-CFG-001", "HD-AUTO-008"}:
        return "logic_review"
    if source.startswith("registry_"):
        return "restore_if_needed" if impacted > 0 or level in {"high", "critical"} else "watch"
    if priority == "optimize":
        return "optimize"
    return "logic_review" if priority == "verify" else "watch"


def _operational_relevance(item, lane):
    priority = str(item.get("priority") or "")
    source_id = str(item.get("source_id") or "")
    level, impacted = _impact(item)
    if priority == "action_now" or source_id == "HD-RES-001" or level in {"critical", "high"}:
        return "high"
    if lane == "watch":
        return "low"
    if impacted > 0 or level == "medium" or lane == "logic_review":
        return "medium"
    return "low"


def _priority_score(item, lane, relevance):
    lane_weight = {"fix_now": 45, "logic_review": 28, "restore_if_needed": 18, "watch": 4, "optimize": 8}.get(lane, 0)
    rel_weight = {"high": 25, "medium": 12, "low": 2}.get(relevance, 0)
    confidence = round(_float(item.get("confidence_score"), 0.5) * 10)
    level, impacted = _impact(item)
    impact = {"critical": 16, "high": 12, "medium": 7, "low": 3, "none": 0}.get(level, 0) + min(10, impacted)
    return min(100, lane_weight + rel_weight + confidence + impact)


def _playbook(item, report, lane, relevance):
    playbook = dict(base._playbook_for(item))
    playbook["model"] = REPAIR_PLAYBOOK_MODEL
    playbook["operational_lane"] = lane
    playbook["operational_relevance"] = relevance
    source_id = str(item.get("source_id") or "")
    source_type = str(item.get("source_type") or "")

    if source_id == "HD-AUTO-003":
        overlaps = _policy_overlap(report)
        if overlaps:
            playbook["category"] = "controller_policy_overlap"
            playbook["repair_readiness"] = "needs_logic_review"
            first = overlaps[0]
            evidence = []
            for conflict in first.get("examples") or []:
                for window in conflict.get("overlap_evidence") or []:
                    evidence.append(window)
            playbook["policy_overlap"] = {
                "entity_id": first.get("entity_id"), "automations": first.get("automations") or [],
                "windows": evidence[:6], "simultaneous_execution_proven": False,
            }
            playbook["steps"] = [
                {"step": 1, "detail": "Examiner les branches de commandes opposées et la fenêtre numérique commune signalée par HA Doctor."},
                {"step": 2, "detail": "Décider quelle politique doit gagner dans cette fenêtre : arrêt, maintien, priorité ou hystérésis explicite."},
                {"step": 3, "detail": "Rendre cet arbitrage statiquement vérifiable par une condition, une priorité ou des seuils disjoints, puis rescanner."},
            ]
            playbook["success_criteria"] = [
                "Aucune fenêtre de politique opposée non arbitrée ne reste sur l'actionneur physique.",
                "HA Doctor peut prouver l'exclusion ou la coordination, ou documente explicitement la concurrence voulue.",
            ]
    elif source_id == "HD-RES-001":
        risky = []
        for rec in (report.get("resilience_recommendations") or {}).get("items") or []:
            if isinstance(rec, dict):
                for name in rec.get("risky_automations") or []:
                    risky.append(str(name))
        playbook["risky_automations"] = sorted(set(risky))[:10]
    elif source_type.startswith("registry_") and lane == "watch":
        playbook["repair_readiness"] = "watch_external"
        playbook["category"] = "external_zero_automation_impact"
        playbook["steps"] = [
            {"step": 1, "detail": "Vérifier si l'équipement ou l'intégration est volontairement hors ligne."},
            {"step": 2, "detail": "Ne restaurer immédiatement que si son usage utilisateur le nécessite ; aucune automatisation n'en dépend actuellement selon le graphe."},
            {"step": 3, "detail": "Conserver l'incident en surveillance et vérifier s'il acquiert un blast radius dans un scan futur."},
        ]
        playbook["success_criteria"] = ["L'incident est soit restauré, soit explicitement toléré sans impact d'automatisation."]
    playbook["automatic_fix"] = False
    playbook["read_only"] = True
    return playbook


def build_entity_attention_v3(report, decisions=None):
    product = report.get("product_intelligence") or {}
    noise = product.get("entity_noise") or {}
    decisions = decisions or []
    registry = [x for x in decisions if str(x.get("source_type") or "").startswith("registry_")]
    watch = [x for x in registry if x.get("operational_lane") == "watch"]
    impacted = [x for x in registry if _impact(x)[1] > 0]
    return {
        "model": ENTITY_ATTENTION_MODEL,
        "raw_unavailable": _int(noise.get("raw_unavailable"), 0),
        "raw_unknown": _int(noise.get("raw_unknown"), 0),
        "raw_attention_candidates": _int(noise.get("unavailable_attention"), 0) + _int(noise.get("unknown_attention"), 0),
        "registry_actionable_root_causes": _int(noise.get("registry_actionable_root_causes"), _int((report.get("root_cause_summary") or {}).get("actionable_registry_incidents"), 0)),
        "registry_decision_count": len(registry),
        "registry_with_automation_impact": len(impacted),
        "registry_zero_impact_watch_count": len(watch),
        "raw_entity_count_used_as_priority": False,
        "operational_principle": "Root cause et blast radius priment sur les compteurs bruts unavailable/unknown.",
    }


def build_decision_engine_v2(report):
    actions = [x for x in (report.get("action_plan") or {}).get("items") or [] if isinstance(x, dict)]
    decisions = []
    for item in actions:
        lane = _operational_lane(item)
        relevance = _operational_relevance(item, lane)
        playbook = _playbook(item, report, lane, relevance)
        score = _priority_score(item, lane, relevance)
        item["repair_playbook"] = playbook
        item["operational_relevance"] = relevance
        item["operational_lane"] = lane
        item["execution_priority_score"] = score
        decisions.append({
            "id": item.get("id"), "title": item.get("title"),
            "priority": item.get("priority"), "severity": item.get("severity"),
            "source_type": item.get("source_type"), "source_id": item.get("source_id"),
            "confidence": item.get("confidence"), "confidence_score": item.get("confidence_score"),
            "dependency_impact": item.get("dependency_impact") or {},
            "operational_relevance": relevance, "operational_lane": lane,
            "execution_priority_score": score, "repair_playbook": playbook,
        })
    lane_rank = {"fix_now": 0, "logic_review": 1, "restore_if_needed": 2, "watch": 3, "optimize": 4}
    decisions.sort(key=lambda x: (lane_rank.get(x.get("operational_lane"), 9), -_int(x.get("execution_priority_score")), -_float(x.get("confidence_score"), 0)))
    lane_counts = Counter(x.get("operational_lane") for x in decisions)
    readiness_counts = Counter((x.get("repair_playbook") or {}).get("repair_readiness") for x in decisions)
    relevance_counts = Counter(x.get("operational_relevance") for x in decisions)
    attention = build_entity_attention_v3(report, decisions)
    batches = {lane: [x.get("id") for x in decisions if x.get("operational_lane") == lane] for lane in ("fix_now", "logic_review", "restore_if_needed", "watch", "optimize")}
    primary = [x for x in decisions if x.get("operational_lane") != "watch"][:10]
    result = {
        "model": DECISION_MODEL, "total": len(decisions), "items": decisions,
        "top": primary[:8], "primary_action_count": len([x for x in decisions if x.get("operational_lane") != "watch"]),
        "lane_counts": dict(lane_counts), "repair_readiness_counts": dict(readiness_counts),
        "operational_relevance_counts": dict(relevance_counts), "repair_batches": batches,
        "ready_for_manual_change_count": readiness_counts.get("ready_for_manual_change", 0),
        "needs_logic_review_count": readiness_counts.get("needs_logic_review", 0),
        "external_dependency_count": readiness_counts.get("external_dependency", 0),
        "watch_external_count": readiness_counts.get("watch_external", 0),
        "entity_attention": attention, "policy_overlap": _policy_overlap(report),
        "automatic_fix": False, "read_only": True,
        "policy": "root_cause_then_operational_lane_then_evidence_then_priority",
    }
    report["decision_engine"] = result
    report.setdefault("product_intelligence", {})["entity_attention"] = attention
    return result
