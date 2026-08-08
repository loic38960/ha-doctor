import json
import re
from collections import Counter, defaultdict
from pathlib import Path

VERSION = "0.6.0"
HISTORY_LIMIT = 20
ENTITY_RE = re.compile(r"\b(?:alarm_control_panel|automation|binary_sensor|button|calendar|camera|climate|counter|cover|device_tracker|input_boolean|input_datetime|input_number|input_select|input_text|lawn_mower|light|lock|media_player|notify|number|person|scene|script|select|sensor|siren|switch|text|time|todo|update|vacuum|weather)\.[a-zA-Z0-9_]+\b")
PRIORITY_ORDER = {"action_now": 0, "verify": 1, "optimize": 2, "info": 3}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
NOISE_RULES_WHEN_ROOT_CAUSES_EXIST = {"HD-ENT-001", "HD-ENT-003"}


def load_history(path="/data/ha-doctor-history.json"):
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)][-HISTORY_LIMIT:]
    except Exception:
        pass
    return []


def save_history(history, path="/data/ha-doctor-history.json"):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(history[-HISTORY_LIMIT:], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _registry_examples(report, explanation):
    registry = report.get("registry_analysis") or {}
    source_type = explanation.get("source_type")
    source_id = str(explanation.get("source_id") or "")
    examples = []
    if source_type == "registry_integration":
        for item in ((registry.get("integration_health") or {}).get("groups") or []):
            if str(item.get("integration") or "") == source_id:
                examples.extend(item.get("examples") or [])
                break
    elif source_type == "registry_device":
        for item in ((registry.get("device_health") or {}).get("groups") or []):
            if str(item.get("name") or "") == source_id:
                examples.extend(item.get("examples") or [])
                break
    elif source_type == "registry_cluster":
        for item in ((registry.get("device_health") or {}).get("groups") or []):
            if source_id in {str(x) for x in (item.get("platforms") or [])} and item.get("status") == "offline":
                examples.extend(item.get("examples") or [])
    return [str(x) for x in examples if isinstance(x, str)]


def _explanation_entities(report, explanation):
    values = []
    for evidence in explanation.get("evidence") or []:
        text = str(evidence.get("text") or "") if isinstance(evidence, dict) else str(evidence)
        values.extend(ENTITY_RE.findall(text))
    values.extend(_registry_examples(report, explanation))
    return sorted(set(x for x in values if ENTITY_RE.fullmatch(x)))


def add_dependency_impact(report, explanations):
    graph = report.get("dependency_graph") or []
    for item in explanations:
        entities = set(_explanation_entities(report, item))
        impacted = []
        trigger_hits = 0
        control_hits = 0
        for node in graph:
            refs = set(node.get("references") or [])
            triggers = set(node.get("triggers_on") or [])
            controls = set(node.get("controls") or [])
            if entities.intersection(refs | triggers | controls):
                name = str(node.get("automation") or "Automatisation")
                impacted.append(name)
                if entities.intersection(triggers):
                    trigger_hits += 1
                if entities.intersection(controls):
                    control_hits += 1
        impacted = sorted(set(impacted))
        count = len(impacted)
        if count >= 3 or control_hits >= 2:
            level, multiplier = "high", 1.20
        elif count >= 1:
            level, multiplier = "medium", 1.08
        else:
            level, multiplier = "low", 1.0
        item["dependency_impact"] = {
            "level": level,
            "impacted_automation_count": count,
            "impacted_automations": impacted[:8],
            "trigger_dependency_count": trigger_hits,
            "control_dependency_count": control_hits,
            "score_multiplier": multiplier,
        }
    return explanations


def add_temporal_context(explanations, history):
    previous = history[-1] if history else None
    prior_ids = [set(x.get("active_ids") or []) for x in history]
    previous_ids = set(previous.get("active_ids") or []) if previous else set()
    for item in explanations:
        item_id = str(item.get("id") or "")
        occurrences = sum(1 for ids in prior_ids if item_id in ids) + 1
        consecutive = 1
        for ids in reversed(prior_ids):
            if item_id in ids:
                consecutive += 1
            else:
                break
        first_seen = None
        for snap in history:
            if item_id in set(snap.get("active_ids") or []):
                first_seen = snap.get("generated_at")
                break
        if not previous:
            status = "baseline"
        elif item_id not in previous_ids and occurrences == 1:
            status = "new"
        elif consecutive >= 2:
            status = "persistent"
        else:
            status = "recurrent"
        source_type = str(item.get("source_type") or "")
        if source_type.startswith("registry_"):
            if status in {"baseline", "new"}:
                factor = 0.72
            elif consecutive == 2:
                factor = 0.90
            else:
                factor = 1.0
        else:
            factor = 1.0
        item["temporal"] = {
            "status": status,
            "occurrences": occurrences,
            "consecutive_scans": consecutive,
            "first_seen": first_seen,
            "persistence_factor": factor,
        }
    return explanations


def _sort_key(item):
    return (
        PRIORITY_ORDER.get(item.get("priority"), 9),
        SEVERITY_ORDER.get(item.get("severity"), 9),
        -float(item.get("confidence_score", 0) or 0),
        item.get("title", ""),
    )


def _plan_explanations(report, explanations):
    root_causes = [x for x in explanations if str(x.get("source_type") or "").startswith("registry_")]
    probable_orphans = int((((report.get("registry_analysis") or {}).get("orphan_analysis") or {}).get("probable_orphan_count", 0) or 0))
    result = []
    suppressed = []
    for item in explanations:
        if item.get("priority") not in {"action_now", "verify", "optimize"}:
            continue
        rule_id = item.get("rule_id")
        if root_causes and rule_id in NOISE_RULES_WHEN_ROOT_CAUSES_EXIST:
            suppressed.append({"id": item.get("id"), "reason": "explained_by_root_causes"})
            continue
        if rule_id == "HD-REG-002" and probable_orphans == 0 and item.get("confidence") == "low":
            suppressed.append({"id": item.get("id"), "reason": "low_confidence_registry_review"})
            continue
        result.append(item)
    return sorted(result, key=_sort_key), suppressed


def _penalty(item):
    priority = item.get("priority")
    severity = item.get("severity")
    table = {
        "action_now": {"critical": 7.0, "high": 5.0, "medium": 3.0, "low": 1.5, "info": 0.0},
        "verify": {"critical": 3.0, "high": 2.0, "medium": 1.4, "low": 0.7, "info": 0.0},
        "optimize": {"critical": 1.0, "high": 0.8, "medium": 0.6, "low": 0.45, "info": 0.0},
    }
    base = table.get(priority, {}).get(severity, 0.0)
    confidence = max(0.45, min(1.0, float(item.get("confidence_score", 0.6) or 0.6)))
    dep = float(((item.get("dependency_impact") or {}).get("score_multiplier", 1.0) or 1.0))
    temporal = float(((item.get("temporal") or {}).get("persistence_factor", 1.0) or 1.0))
    return base * confidence * dep * temporal


def build_score_v3(report, plan_items, history):
    domain_penalties = defaultdict(float)
    breakdown = []
    for item in plan_items:
        p = _penalty(item)
        if p <= 0:
            continue
        domain = str(item.get("domain") or "configuration")
        domain_penalties[domain] += p
        breakdown.append({
            "id": item.get("id"),
            "domain": domain,
            "penalty": round(p, 2),
            "temporal_status": (item.get("temporal") or {}).get("status"),
            "dependency_impact": (item.get("dependency_impact") or {}).get("level"),
        })
    total_penalty = min(50.0, sum(domain_penalties.values()))
    global_score = int(round(max(50.0, 100.0 - total_penalty)))
    domain_names = ["system", "entities", "automations", "configuration", "security", "performance"]
    domains = {}
    for domain in domain_names:
        penalty = domain_penalties.get(domain, 0.0)
        domains[domain] = int(round(max(50.0, 100.0 - min(50.0, penalty * 2.35))))
    previous_score = None
    if history:
        previous_score = history[-1].get("health_score_v3")
    return {
        "global": global_score,
        "domains": domains,
        "penalty_total": round(total_penalty, 2),
        "penalty_breakdown": breakdown,
        "previous_score": previous_score,
    }


def _action_item(explanation):
    checks = explanation.get("checks") or []
    return {
        "id": explanation.get("id"),
        "title": explanation.get("title"),
        "priority": explanation.get("priority"),
        "priority_label": explanation.get("priority_label"),
        "severity": explanation.get("severity"),
        "domain": explanation.get("domain"),
        "confidence": explanation.get("confidence"),
        "confidence_label": explanation.get("confidence_label"),
        "confidence_score": explanation.get("confidence_score"),
        "diagnosis": explanation.get("diagnosis"),
        "impact": explanation.get("impact"),
        "first_check": checks[0] if checks else None,
        "source_type": explanation.get("source_type"),
        "source_id": explanation.get("source_id"),
        "temporal": explanation.get("temporal"),
        "dependency_impact": explanation.get("dependency_impact"),
    }


def _health_label(score):
    if score is None:
        return "Inconnu"
    if score >= 92:
        return "Excellent"
    if score >= 82:
        return "Bon"
    if score >= 70:
        return "À surveiller"
    if score >= 55:
        return "À corriger"
    return "Critique"


def enrich_v060(report, history_path="/data/ha-doctor-history.json"):
    history = load_history(history_path)
    legacy_score = (report.get("scores") or {}).get("global")
    explanations = list(report.get("diagnostic_explanations") or [])
    add_dependency_impact(report, explanations)
    add_temporal_context(explanations, history)
    explanations.sort(key=_sort_key)

    plan_items, suppressed = _plan_explanations(report, explanations)
    score = build_score_v3(report, plan_items, history)
    report["scores"] = {"global": score["global"], "domains": score["domains"]}

    counts = Counter(x.get("priority") for x in plan_items)
    action_items = [_action_item(x) for x in plan_items]
    report["action_plan"] = {
        "total": len(action_items),
        "displayed": len(action_items),
        "remaining": 0,
        "counts": {
            "action_now": counts.get("action_now", 0),
            "verify": counts.get("verify", 0),
            "optimize": counts.get("optimize", 0),
        },
        "items": action_items,
        "top": action_items[:5],
        "suppressed_noise": suppressed,
        "note": "Plan 0.6 corrélé : les volumes bruts d'entités ne sont pas répétés comme actions lorsqu'une cause racine les explique déjà.",
    }

    current_ids = [str(x.get("id")) for x in plan_items if x.get("id")]
    previous_ids = set(history[-1].get("active_ids") or []) if history else set()
    current_set = set(current_ids)
    resolved = sorted(previous_ids - current_set)
    new_ids = sorted(current_set - previous_ids) if history else []
    persistent_ids = sorted(current_set & previous_ids) if history else []

    root_causes = [x for x in plan_items if str(x.get("source_type") or "").startswith("registry_")]
    observations = report.get("registry_observations") or []
    report["root_cause_summary"] = {
        "actionable_registry_incidents": len(root_causes),
        "integration_incidents": sum(1 for x in root_causes if x.get("source_type") == "registry_integration"),
        "device_incidents": sum(1 for x in root_causes if x.get("source_type") == "registry_device"),
        "cluster_incidents": sum(1 for x in root_causes if x.get("source_type") == "registry_cluster"),
        "transient_observations": len(observations),
    }

    score_history = [
        {"generated_at": x.get("generated_at"), "score": x.get("health_score_v3")}
        for x in history[-9:] if x.get("health_score_v3") is not None
    ]
    score_history.append({"generated_at": report.get("generated_at"), "score": score["global"]})
    report["temporal_analysis"] = {
        "enabled": True,
        "history_limit": HISTORY_LIMIT,
        "scan_count": min(HISTORY_LIMIT, len(history) + 1),
        "previous_score": score["previous_score"],
        "score_delta": None if score["previous_score"] is None else score["global"] - int(score["previous_score"]),
        "new_count": len(new_ids),
        "persistent_count": len(persistent_ids),
        "resolved_since_previous_count": len(resolved),
        "new_ids": new_ids[:12],
        "persistent_ids": persistent_ids[:12],
        "resolved_since_previous": resolved[:12],
        "score_history": score_history,
        "note": "L'historique local ne conserve que des compteurs, scores et identifiants de diagnostics ; aucune valeur brute d'état n'est stockée.",
    }

    report["diagnostic_explanations"] = explanations[:50]
    engine = dict(report.get("diagnostic_engine") or {})
    engine.update({
        "version": "explain_v2_temporal",
        "root_cause_calibration": "root_cause_v2",
        "temporal_analysis": True,
        "dependency_impact_analysis": True,
        "plan_noise_suppressed_count": len(suppressed),
        "registry_incident_count": len(root_causes),
    })
    report["diagnostic_engine"] = engine

    report["score_meta"] = {
        "model": "root_cause_temporal_v1",
        "alpha": True,
        "legacy_global": legacy_score,
        "previous_global": score["previous_score"],
        "root_cause_scoring": True,
        "temporal_scoring": True,
        "dependency_scoring": True,
        "raw_entity_volume_scoring": False,
        "penalty_total": score["penalty_total"],
        "note": "0.6 calcule l'indice à partir des diagnostics corrélés, de leur confiance, de leur persistance et de leur impact sur les automatisations. Les volumes unavailable/unknown ne sont plus pénalisés une seconde fois lorsqu'une cause racine les explique.",
    }

    top = [x for x in plan_items if x.get("priority") == "action_now"][:3]
    top_titles = [str(x.get("title")) for x in top if x.get("title")]
    sentences = [f"Indice de santé V3 {score['global']}/100 ({_health_label(score['global'])})."]
    sentences.append(f"{counts.get('action_now', 0)} correction(s) prioritaire(s), {counts.get('verify', 0)} point(s) à vérifier et {counts.get('optimize', 0)} optimisation(s) après déduplication des causes racines.")
    sentences.append(f"{len(root_causes)} incident(s) de registre réellement retenu(s) dans le plan d'action.")
    if score["previous_score"] is not None:
        delta = score["global"] - int(score["previous_score"])
        sentences.append(f"Évolution depuis le scan précédent : {delta:+d} point(s).")
    if resolved:
        sentences.append(f"{len(resolved)} diagnostic(s) ne sont plus présents depuis le scan précédent.")
    if top_titles:
        sentences.append("Priorités actuelles : " + " ; ".join(top_titles) + ".")
    report["executive_summary"] = {
        "health_score": score["global"],
        "health_label": _health_label(score["global"]),
        "text": " ".join(sentences),
        "top_priority_titles": top_titles,
        "registry_available": bool((report.get("registry_analysis") or {}).get("available")),
        "root_cause_count": len(root_causes),
    }

    report.setdefault("privacy", {})["temporal_history_raw_states_persisted"] = False
    report["privacy"]["temporal_history_secret_values_persisted"] = False
    report["privacy"]["temporal_history_scope"] = "diagnostic_ids_counts_scores_only"

    snapshot = {
        "generated_at": report.get("generated_at"),
        "health_score_v3": score["global"],
        "legacy_score": legacy_score,
        "active_ids": current_ids,
        "registry_ids": [str(x.get("id")) for x in root_causes if x.get("id")],
        "priority_counts": report["action_plan"]["counts"],
        "unavailable_count": (report.get("inventory") or {}).get("unavailable_count"),
        "unknown_count": (report.get("inventory") or {}).get("unknown_count"),
    }
    history.append(snapshot)
    save_history(history, history_path)
    report["version"] = VERSION
    return report
