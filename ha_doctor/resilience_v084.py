"""HA Doctor 0.8.4 resilience recommendations.

Turns high-criticality partially protected external dependencies into an
actionable, non-scoring recommendation.
"""
from collections import Counter

VERSION = "0.8.4"
MODEL = "resilience_recommendations_v1"
RULE_ID = "HD-RES-001"
DIAGNOSTIC_ID = "DX-HD-RES-001"


def _priority_rank(value):
    return {"action_now": 0, "verify": 1, "optimize": 2, "info": 3}.get(str(value or "info"), 9)


def _severity_rank(value):
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(str(value or "info"), 9)


def _sync_sections(report):
    plan = report.setdefault("action_plan", {})
    items = plan.get("items") or []
    items.sort(key=lambda item: (
        _priority_rank(item.get("priority")),
        _severity_rank(item.get("severity")),
        -float(item.get("confidence_score", 0) or 0),
        str(item.get("title") or ""),
    ))
    counts = Counter(str(item.get("priority") or "info") for item in items)
    plan.update({
        "items": items,
        "top": items[:6],
        "total": len(items),
        "displayed": len(items),
        "remaining": 0,
        "counts": {
            "action_now": counts.get("action_now", 0),
            "verify": counts.get("verify", 0),
            "optimize": counts.get("optimize", 0),
        },
    })
    queue = report.setdefault("recommendation_queue", {})
    queue["items"] = [dict(item) for item in items]
    queue["total"] = len(items)
    summary = report.setdefault("diagnostic_summary", {})
    summary["priority_counts"] = {
        "action_now": counts.get("action_now", 0),
        "verify": counts.get("verify", 0),
        "optimize": counts.get("optimize", 0),
        "info": 0,
    }
    summary["actionable_count"] = counts.get("action_now", 0) + counts.get("verify", 0)
    summary["plan_id_count"] = len(items)
    summary["headline"] = (
        f"{counts.get('action_now',0)} correction(s) prioritaire(s), "
        f"{counts.get('verify',0)} point(s) à vérifier et "
        f"{counts.get('optimize',0)} optimisation(s)."
    )


def build_resilience_recommendations_v1(report):
    report["findings"] = [item for item in report.get("findings") or [] if str(item.get("rule_id") or "") != RULE_ID]
    report["diagnostic_explanations"] = [item for item in report.get("diagnostic_explanations") or [] if str(item.get("id") or "") != DIAGNOSTIC_ID]
    for section_name in ("action_plan", "recommendation_queue"):
        section = report.get(section_name) or {}
        section["items"] = [item for item in section.get("items") or [] if str(item.get("id") or "") != DIAGNOSTIC_ID]

    resilience = report.get("resilience_analysis") or {}
    candidates = []
    for item in resilience.get("items") or []:
        if not item.get("counts_as_external_spof"):
            continue
        if str(item.get("status") or "") not in {"partial", "review"}:
            continue
        criticality = int(item.get("criticality", 0) or 0)
        unprotected = int(item.get("unprotected_count", 0) or 0)
        if criticality < 60 or unprotected <= 0:
            continue
        candidates.append(item)
    candidates.sort(key=lambda item: (-int(item.get("criticality", 0) or 0), -int(item.get("unprotected_count", 0) or 0), str(item.get("entity_id") or "")))
    top = candidates[:3]
    if not top:
        report["resilience_recommendations"] = {"model": MODEL, "count": 0, "items": [], "scoring_applied": False}
        _sync_sections(report)
        return report["resilience_recommendations"]

    examples = []
    evidence = []
    affected_automations = set()
    for item in top:
        unprotected_automations = [
            str(entry.get("automation") or "")
            for entry in item.get("automation_evidence") or []
            if str(entry.get("protection") or "") == "none"
        ]
        affected_automations.update(x for x in unprotected_automations if x)
        example = {
            "entity_id": item.get("entity_id"),
            "criticality": int(item.get("criticality", 0) or 0),
            "automation_count": int(item.get("automation_count", 0) or 0),
            "explicit_guard_count": int(item.get("explicit_guard_count", 0) or 0),
            "numeric_default_only_count": int(item.get("numeric_default_only_count", 0) or 0),
            "unprotected_count": int(item.get("unprotected_count", 0) or 0),
            "unprotected_automations": unprotected_automations[:10],
        }
        examples.append(example)
        evidence.append({
            "type": "dependency",
            "label": str(item.get("entity_id") or "Dépendance"),
            "text": f"criticité {example['criticality']}/100 · {example['unprotected_count']} automatisation(s) sans garde forte",
        })

    severity = "medium" if int(top[0].get("criticality", 0) or 0) >= 80 else "low"
    title = "Dépendance externe critique insuffisamment protégée"
    summary = (
        f"{len(top)} dépendance(s) externe(s) critique(s) ont encore des automatisations "
        "sans garde explicite contre unavailable/unknown."
    )
    finding = {
        "rule_id": RULE_ID,
        "title": title,
        "severity": severity,
        "domain": "automations",
        "summary": summary,
        "recommendation": (
            "Ajouter une garde explicite ou une stratégie de repli aux automatisations les plus "
            "critiques avant d'élargir la logique autour de cette dépendance."
        ),
        "examples": examples,
        "priority": "verify",
        "priority_label": "À vérifier",
    }
    report.setdefault("findings", []).append(finding)

    explanation = {
        "id": DIAGNOSTIC_ID,
        "source_type": "finding",
        "source_id": RULE_ID,
        "rule_id": RULE_ID,
        "title": title,
        "priority": "verify",
        "priority_label": "À vérifier",
        "severity": severity,
        "domain": "automations",
        "confidence": "high",
        "confidence_label": "Élevée",
        "confidence_score": 0.90,
        "diagnosis": summary,
        "impact": (
            "Si la source externe devient unavailable ou unknown, certaines automatisations peuvent "
            "continuer avec une valeur implicite, ne rien faire ou prendre une décision incohérente."
        ),
        "probable_causes": [
            "dépendance devenue centrale au fil des automatisations",
            "conditions unavailable/unknown ajoutées seulement sur les scénarios les plus récents",
            "fallback numérique utilisé sans garde métier explicite",
        ],
        "evidence": evidence[:10],
        "checks": [
            {
                "step": 1,
                "title": "Commencer par la dépendance la plus critique",
                "detail": f"Examiner {top[0].get('entity_id')} et les automatisations listées sans protection forte.",
            },
            {
                "step": 2,
                "title": "Définir le comportement en cas de donnée absente",
                "detail": "Choisir explicitement : ne rien faire, conserver le dernier état, utiliser une valeur sûre ou notifier.",
            },
            {
                "step": 3,
                "title": "Tester unavailable et unknown séparément",
                "detail": "Les deux états ne doivent pas être traités comme une valeur numérique normale.",
            },
        ],
        "resolution_goal": "Chaque dépendance externe critique doit avoir un comportement déterministe lorsqu'elle ne fournit plus de donnée exploitable.",
        "safe_to_ignore_when": "Si l'effet métier de chaque automatisation concernée est explicitement sûr en cas d'absence de donnée.",
        "automatic_fix": False,
        "read_only": True,
        "dependency_impact": {
            "model": MODEL,
            "level": "high" if severity == "medium" else "medium",
            "impacted_automation_count": len(affected_automations),
            "impacted_automations": sorted(affected_automations)[:20],
            "weighted_impact_score": round(sum(int(item.get("criticality", 0) or 0) for item in top) / 10.0, 2),
            "score_multiplier": 1.0,
            "scoring_applied": False,
        },
    }
    report.setdefault("diagnostic_explanations", []).append(explanation)
    action_item = {key: explanation.get(key) for key in (
        "id", "title", "priority", "priority_label", "severity", "domain",
        "confidence", "confidence_label", "confidence_score", "diagnosis", "impact",
        "source_type", "source_id", "dependency_impact",
    )}
    action_item["why_now"] = "La dépendance est à forte criticité et plusieurs automatisations n'ont pas de garde explicite."
    action_item["first_check"] = explanation["checks"][0]
    report.setdefault("action_plan", {}).setdefault("items", []).append(action_item)
    _sync_sections(report)

    result = {
        "model": MODEL,
        "count": len(top),
        "items": examples,
        "action_plan_diagnostic_id": DIAGNOSTIC_ID,
        "scoring_applied": False,
        "note": "Cette recommandation enrichit le plan mais ne retire aucun point au score tant que la calibration n'est pas validée sur plusieurs installations.",
    }
    report["resilience_recommendations"] = result
    report.setdefault("diagnostic_engine", {})["resilience_recommendations"] = True
    return result
