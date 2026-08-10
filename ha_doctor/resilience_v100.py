"""Exposure-first resilience recommendation calibration for HA Doctor 0.10.

The validated V4 role analysis is preserved. This layer changes only which
external SPOFs are promoted into the action plan: an actually unprotected
physical controller outranks a high-criticality dependency that merely has a
weak fallback.
"""

import resilience_v088 as base
from contracts_v100 import RESILIENCE_RECOMMENDATION_MODEL

RULE_ID = "HD-RES-001"
DIAGNOSTIC_ID = "DX-HD-RES-001"


def _int(value):
    try:
        return int(value or 0)
    except Exception:
        return 0


def _remove_previous(report):
    base._remove_previous_recommendation(report)


def _risk_entries(item):
    return [
        entry for entry in item.get("automation_evidence") or []
        if isinstance(entry, dict)
        and entry.get("risk_relevant")
        and str(entry.get("protection") or "") in {"none", "weak"}
    ]


def build_resilience_recommendations_v3(report):
    _remove_previous(report)
    analysis = report.get("resilience_analysis") or {}
    external = [
        item for item in analysis.get("items") or []
        if isinstance(item, dict) and item.get("counts_as_external_spof")
    ]

    unprotected = [
        item for item in external
        if _int(item.get("unprotected_physical_automation_count")) > 0
    ]
    weak_high = [
        item for item in external
        if _int(item.get("unprotected_physical_automation_count")) == 0
        and _int(item.get("weak_physical_automation_count")) > 0
        and _int(item.get("criticality")) >= 60
    ]

    unprotected.sort(key=lambda item: (
        -_int(item.get("unprotected_physical_automation_count")),
        -_int(item.get("criticality")),
        str(item.get("entity_id") or ""),
    ))
    weak_high.sort(key=lambda item: (
        -_int(item.get("criticality")),
        -_int(item.get("weak_physical_automation_count")),
        str(item.get("entity_id") or ""),
    ))

    selected = (unprotected[:2] + weak_high[:1])[:3]
    if not selected:
        result = {
            "model": RESILIENCE_RECOMMENDATION_MODEL,
            "count": 0,
            "must_fix_count": 0,
            "hardening_count": 0,
            "items": [],
            "scoring_applied": False,
            "selection_policy": "unprotected_physical_before_weak_high_criticality",
            "note": "Aucun contrôle physique externe réellement exposé ne nécessite de recommandation prioritaire.",
        }
        report["resilience_recommendations"] = result
        return result

    examples = []
    evidence = []
    affected = set()
    for item in selected:
        risky = _risk_entries(item)
        names = [str(entry.get("automation") or "") for entry in risky if entry.get("automation")]
        affected.update(names)
        unprotected_count = _int(item.get("unprotected_physical_automation_count"))
        weak_count = _int(item.get("weak_physical_automation_count"))
        tier = "must_fix" if unprotected_count else "hardening"
        example = {
            "entity_id": item.get("entity_id"),
            "tier": tier,
            "criticality": _int(item.get("criticality")),
            "automation_count": _int(item.get("automation_count")),
            "physical_control_consumer_count": _int(item.get("physical_control_consumer_count")),
            "unprotected_physical_automation_count": unprotected_count,
            "weak_physical_automation_count": weak_count,
            "risky_automations": names[:10],
        }
        examples.append(example)
        wording = "non protégé" if tier == "must_fix" else "fallback faible"
        evidence.append({
            "type": "dependency",
            "label": str(item.get("entity_id") or "Dépendance"),
            "text": (
                f"{wording} · criticité {example['criticality']}/100 · "
                f"{unprotected_count} contrôle(s) non protégé(s) · {weak_count} fallback(s) faible(s)"
            ),
        })

    must_fix_count = sum(1 for item in examples if item["tier"] == "must_fix")
    hardening_count = len(examples) - must_fix_count
    severity = "medium" if must_fix_count else "low"
    title = "Dépendance externe à sécuriser sur un contrôle physique"
    summary = (
        f"{must_fix_count} dépendance(s) ont un contrôle physique réellement non protégé"
        + (f" ; {hardening_count} dépendance(s) supplémentaire(s) n'ont qu'un fallback faible." if hardening_count else ".")
    )

    report.setdefault("findings", []).append({
        "rule_id": RULE_ID,
        "title": title,
        "severity": severity,
        "domain": "automations",
        "summary": summary,
        "recommendation": (
            "Traiter d'abord les contrôles physiques sans garde, puis renforcer les fallbacks faibles des dépendances très critiques."
        ),
        "examples": examples,
        "priority": "verify",
        "priority_label": "À vérifier",
    })

    first = examples[0]
    first_names = first.get("risky_automations") or []
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
        "confidence_score": 0.94,
        "diagnosis": summary,
        "impact": "Une donnée externe invalide peut encore influencer directement au moins un contrôle physique.",
        "evidence": evidence[:10],
        "checks": [{
            "step": 1,
            "title": "Commencer par le contrôle réellement non protégé" if must_fix_count else "Renforcer le fallback faible",
            "detail": (
                f"Vérifier {first.get('entity_id')} dans "
                f"{', '.join(first_names[:3]) or 'les automatisations listées'}."
            ),
        }],
        "automatic_fix": False,
        "read_only": True,
        "dependency_impact": {
            "model": RESILIENCE_RECOMMENDATION_MODEL,
            "level": "high" if must_fix_count else "medium",
            "impacted_automation_count": len(affected),
            "impacted_automations": sorted(affected)[:20],
            "weighted_impact_score": round(sum(_int(item.get("criticality")) for item in selected) / 10.0, 2),
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
    action_item["why_now"] = (
        "Un contrôle physique est réellement non protégé ; il passe avant les dépendances seulement faiblement protégées."
        if must_fix_count else "Une dépendance très critique n'a encore qu'un fallback faible."
    )
    action_item["first_check"] = explanation["checks"][0]
    report.setdefault("action_plan", {}).setdefault("items", []).append(action_item)

    result = {
        "model": RESILIENCE_RECOMMENDATION_MODEL,
        "count": len(selected),
        "must_fix_count": must_fix_count,
        "hardening_count": hardening_count,
        "items": examples,
        "action_plan_diagnostic_id": DIAGNOSTIC_ID,
        "scoring_applied": False,
        "selection_policy": "unprotected_physical_before_weak_high_criticality",
        "note": "La criticité ne peut plus masquer un contrôle physique réellement non protégé situé sous l'ancien seuil de 60.",
    }
    report["resilience_recommendations"] = result
    return result
