"""HA Doctor 0.13 evidence-first decision and repair playbooks.

This module never edits Home Assistant. It turns correlated diagnostics into a
small operational decision board with concrete manual verification/repair steps,
success criteria and explicit readiness.
"""

from collections import Counter
from contracts_v130 import DECISION_MODEL, ENTITY_ATTENTION_MODEL, REPAIR_PLAYBOOK_MODEL


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def _impact(item):
    dep = item.get("dependency_impact") or {}
    return str(dep.get("level") or "none"), _int(dep.get("impacted_automation_count"), 0)


def _operational_relevance(item):
    level, count = _impact(item)
    priority = str(item.get("priority") or "")
    source = str(item.get("source_type") or "")
    source_id = str(item.get("source_id") or "")
    if priority == "action_now" or level in {"critical", "high"} or source_id == "HD-RES-001":
        return "high"
    if count > 0 or level == "medium":
        return "medium"
    if source.startswith("registry_") and count == 0:
        return "low"
    return "medium" if priority == "verify" else "low"


def _playbook_for(item):
    source_id = str(item.get("source_id") or "")
    source_type = str(item.get("source_type") or "")
    title = str(item.get("title") or "Diagnostic")
    evidence = str(item.get("evidence_level") or item.get("confidence") or "")

    readiness = "needs_logic_review"
    steps = []
    success = []
    category = "logic_review"

    if source_id == "HD-AUTO-009":
        readiness = "ready_for_manual_change"; category = "automation_ownership"
        steps = [
            "Identifier les deux automatisations qui écrivent le même helper et choisir un seul propriétaire canonique.",
            "Supprimer ou neutraliser uniquement l'écriture redondante, sans modifier les autres conditions de contrôle.",
            "Relancer un scan et vérifier que le double writer a disparu sans nouvelle référence manquante.",
        ]
        success = ["Un seul writer reste pour chaque compteur concerné.", "HD-AUTO-009 disparaît du plan d'action."]
    elif source_id == "HD-SEC-001":
        readiness = "ready_for_manual_change"; category = "secret_hygiene"
        steps = [
            "Ouvrir uniquement les fichiers et clés signalés par HA Doctor, sans recopier la valeur sensible.",
            "Déplacer la valeur vers le mécanisme de secret approprié et remplacer le littéral par une référence.",
            "Si la valeur a été publiée dans un dépôt ou une sauvegarde partageable, la faire tourner côté service concerné.",
        ]
        success = ["Aucun indice de secret actif ne reste dans la configuration scannée.", "Aucune valeur de secret n'apparaît dans le rapport HA Doctor."]
    elif source_id == "HD-CFG-006":
        readiness = "ready_for_manual_change"; category = "sensor_semantics"
        steps = [
            "Confirmer l'intention du capteur : durée d'activation ou intégration d'une grandeur numérique.",
            "Pour une durée ON/OFF, remplacer l'Integral sur switch par un capteur de durée adapté ; pour une énergie, utiliser une source de puissance numérique.",
            "Vérifier unité, device_class et résultat après redémarrage/rechargement manuel de Home Assistant.",
        ]
        success = ["La source de l'intégration est numérique, ou le besoin de durée utilise un capteur de durée.", "HD-CFG-006 disparaît."]
    elif source_id == "HD-AUTO-005":
        readiness = "ready_for_manual_change"; category = "automation_cleanup"
        steps = [
            "Comparer les deux actions consécutives signalées : service, cible et données.",
            "Si elles sont strictement identiques et sans effet volontaire de répétition, supprimer une seule occurrence.",
            "Tester l'automatisation manuellement puis relancer HA Doctor.",
        ]
        success = ["Aucune action consécutive strictement identique ne reste sur ce chemin."]
    elif source_id == "HD-AUTO-003":
        readiness = "needs_logic_review"; category = "controller_arbitration"
        steps = [
            "Commencer par les paires physiques restantes, avant les helpers.",
            "Utiliser la matrice de garde-fous et les fenêtres numériques pour décider si les contrôleurs sont exclusifs, coordonnés ou réellement concurrents.",
            "En cas de concurrence réelle, ajouter une priorité explicite, une exclusion mutuelle ou un interlock vérifiable.",
        ]
        success = ["Chaque paire physique est soit prouvée exclusive/coordonnée, soit protégée par une règle d'arbitrage explicite."]
    elif source_id == "HD-RES-001":
        readiness = "needs_logic_review"; category = "dependency_guard"
        steps = [
            "Identifier la donnée externe et les automatisations physiques qui en dépendent.",
            "Définir un comportement sûr quand la donnée est unavailable/unknown ou trop ancienne.",
            "Tester séparément la perte de donnée et son retour avant de considérer la protection suffisante.",
        ]
        success = ["Aucun contrôle physique critique ne dépend d'une donnée externe sans garde ou fallback explicite."]
    elif source_id == "HD-CFG-001":
        readiness = "needs_logic_review"; category = "missing_reference"
        steps = [
            "Vérifier si chaque entity_id absent a été renommé, supprimé ou appartient à une intégration actuellement hors ligne.",
            "Mettre à jour uniquement les références dont le remplacement est certain ; ne pas deviner un nouvel entity_id.",
            "Relancer HA Doctor pour confirmer la disparition des références corrigées.",
        ]
        success = ["Les références restantes correspondent à des entités réellement attendues et existantes."]
    elif source_type.startswith("registry_"):
        readiness = "external_dependency"; category = "external_restore"
        steps = [
            "Vérifier d'abord si l'intégration ou l'appareil est volontairement hors ligne.",
            "Si non, restaurer la connectivité/authentification depuis Home Assistant ou l'équipement concerné.",
            "Ne traiter en priorité que les incidents qui ont un impact d'automatisation ou un usage réel.",
        ]
        success = ["L'intégration/appareil redevient disponible, ou l'incident est explicitement classé comme attendu et sans impact."]
    elif str(item.get("priority") or "") == "optimize":
        readiness = "optimization"; category = "optimization"
        steps = [
            "Vérifier que l'optimisation ne change pas le comportement fonctionnel attendu.",
            "Appliquer une seule simplification à la fois puis comparer le scan avant/après.",
        ]
        success = ["Le comportement reste identique et le diagnostic d'optimisation disparaît ou diminue."]
    else:
        readiness = "observe_only" if str(item.get("priority") or "") == "info" else "needs_logic_review"
        steps = ["Examiner l'évidence HA Doctor et confirmer le diagnostic avant toute modification.", "Effectuer une seule modification à la fois puis relancer un scan."]
        success = [f"Le diagnostic « {title} » est soit confirmé et corrigé, soit reclassé avec une preuve explicite."]

    return {
        "model": REPAIR_PLAYBOOK_MODEL,
        "category": category,
        "repair_readiness": readiness,
        "evidence_tier": evidence,
        "steps": [{"step": i + 1, "detail": text} for i, text in enumerate(steps)],
        "success_criteria": success,
        "automatic_fix": False,
        "read_only": True,
        "rollback_principle": "Une modification à la fois ; conserver la version précédente et la restaurer si le comportement régresse.",
    }


def build_entity_attention_v2(report):
    product = report.get("product_intelligence") or {}
    noise = product.get("entity_noise") or {}
    actions = [x for x in (report.get("action_plan") or {}).get("items") or [] if isinstance(x, dict)]
    registry_actions = [x for x in actions if str(x.get("source_type") or "").startswith("registry_")]
    zero_impact = [x for x in registry_actions if _impact(x)[1] == 0]
    impacted = [x for x in registry_actions if _impact(x)[1] > 0]
    high_dep = [x for x in actions if _impact(x)[0] in {"critical", "high"}]
    return {
        "model": ENTITY_ATTENTION_MODEL,
        "raw_unavailable": _int(noise.get("raw_unavailable"), 0),
        "raw_unknown": _int(noise.get("raw_unknown"), 0),
        "raw_attention_candidates": _int(noise.get("unavailable_attention"), 0) + _int(noise.get("unknown_attention"), 0),
        "registry_actionable_root_causes": _int(noise.get("registry_actionable_root_causes"), _int((report.get("root_cause_summary") or {}).get("actionable_registry_incidents"), 0)),
        "registry_actions": len(registry_actions),
        "registry_actions_with_automation_impact": len(impacted),
        "registry_actions_without_automation_impact": len(zero_impact),
        "high_dependency_diagnostic_count": len(high_dep),
        "operational_principle": "Les compteurs bruts restent visibles mais ne déterminent jamais seuls l'ordre d'action ; l'usage réel et l'impact d'automatisation priment.",
    }


def build_decision_engine(report):
    actions = [x for x in (report.get("action_plan") or {}).get("items") or [] if isinstance(x, dict)]
    decisions = []
    for item in actions:
        playbook = _playbook_for(item)
        relevance = _operational_relevance(item)
        item["repair_playbook"] = playbook
        item["operational_relevance"] = relevance
        decisions.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "priority": item.get("priority"),
            "severity": item.get("severity"),
            "source_type": item.get("source_type"),
            "source_id": item.get("source_id"),
            "confidence": item.get("confidence"),
            "confidence_score": item.get("confidence_score"),
            "dependency_impact": item.get("dependency_impact") or {},
            "operational_relevance": relevance,
            "repair_playbook": playbook,
        })

    relevance_rank = {"high": 0, "medium": 1, "low": 2}
    readiness_rank = {"ready_for_manual_change": 0, "needs_logic_review": 1, "external_dependency": 2, "optimization": 3, "observe_only": 4}
    decisions.sort(key=lambda x: (
        relevance_rank.get(x.get("operational_relevance"), 9),
        readiness_rank.get((x.get("repair_playbook") or {}).get("repair_readiness"), 9),
        -float(x.get("confidence_score") or 0),
    ))
    counts = Counter((x.get("repair_playbook") or {}).get("repair_readiness") for x in decisions)
    relevance_counts = Counter(x.get("operational_relevance") for x in decisions)
    attention = build_entity_attention_v2(report)
    result = {
        "model": DECISION_MODEL,
        "total": len(decisions),
        "repair_readiness_counts": dict(counts),
        "operational_relevance_counts": dict(relevance_counts),
        "ready_for_manual_change_count": counts.get("ready_for_manual_change", 0),
        "needs_logic_review_count": counts.get("needs_logic_review", 0),
        "external_dependency_count": counts.get("external_dependency", 0),
        "top": decisions[:8],
        "items": decisions,
        "entity_attention": attention,
        "automatic_fix": False,
        "read_only": True,
        "policy": "evidence_then_operational_impact_then_repair_readiness",
    }
    report["decision_engine"] = result
    report.setdefault("product_intelligence", {})["entity_attention"] = attention
    return result
