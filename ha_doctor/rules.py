from collections import defaultdict

SEVERITY_PENALTY = {
    "critical": 30,
    "high": 15,
    "medium": 7,
    "low": 3,
    "info": 0,
}

DOMAIN_LABELS = {
    "system": "Système",
    "entities": "Entités",
    "automations": "Automatisations",
    "configuration": "Configuration",
}


def finding(rule_id, title, severity, domain, summary, recommendation, **extra):
    item = {
        "rule_id": rule_id,
        "title": title,
        "severity": severity,
        "domain": domain,
        "summary": summary,
        "recommendation": recommendation,
    }
    item.update({k: v for k, v in extra.items() if v is not None})
    return item


def evaluate(snapshot):
    findings = []
    states = snapshot.get("states", [])
    yaml_analysis = snapshot.get("yaml", {})
    automations = yaml_analysis.get("automations", [])

    # System/API availability
    if snapshot.get("api_errors"):
        findings.append(finding(
            "HD-SYS-001",
            "Certaines informations système sont inaccessibles",
            "low",
            "system",
            f"{len(snapshot['api_errors'])} appel(s) d'information n'ont pas répondu correctement.",
            "Vérifier les journaux HA Doctor. Le scan principal reste volontairement limité à des API en lecture seule.",
        ))

    # Entity health
    unavailable = [s for s in states if s.get("state") == "unavailable"]
    unknown = [s for s in states if s.get("state") == "unknown"]
    total = max(len(states), 1)
    unavailable_ratio = len(unavailable) / total

    if len(unavailable) >= 10 or unavailable_ratio >= 0.05:
        sev = "high" if unavailable_ratio >= 0.10 else "medium"
        findings.append(finding(
            "HD-ENT-001",
            "Nombre important d'entités indisponibles",
            sev,
            "entities",
            f"{len(unavailable)} entité(s) sont actuellement unavailable sur {len(states)} états.",
            "Identifier les intégrations ou appareils communs à ces entités avant de supprimer quoi que ce soit.",
            examples=[x.get("entity_id") for x in unavailable[:12]],
        ))
    elif unavailable:
        findings.append(finding(
            "HD-ENT-002",
            "Entités indisponibles détectées",
            "low",
            "entities",
            f"{len(unavailable)} entité(s) sont actuellement unavailable.",
            "Vérifier si ces indisponibilités sont temporaires ou correspondent à d'anciens appareils.",
            examples=[x.get("entity_id") for x in unavailable[:10]],
        ))

    if len(unknown) >= 10:
        findings.append(finding(
            "HD-ENT-003",
            "Plusieurs entités ont un état inconnu",
            "medium",
            "entities",
            f"{len(unknown)} entité(s) sont actuellement unknown.",
            "Contrôler leur intégration et leur disponibilité au démarrage de Home Assistant.",
            examples=[x.get("entity_id") for x in unknown[:10]],
        ))

    # Missing entity references in YAML
    missing_refs = yaml_analysis.get("missing_entity_references", [])
    if missing_refs:
        sev = "medium" if len(missing_refs) >= 5 else "low"
        findings.append(finding(
            "HD-CFG-001",
            "Références d'entités absentes détectées dans le YAML",
            sev,
            "configuration",
            f"{len(missing_refs)} référence(s) pointent vers des entity_id qui ne figurent pas dans les états actuels.",
            "Vérifier les références avant suppression : les templates dynamiques et certains contextes peuvent produire des faux positifs.",
            examples=missing_refs[:15],
        ))

    # Potential inline secrets: never include values
    inline_secrets = yaml_analysis.get("potential_inline_secrets", [])
    if inline_secrets:
        findings.append(finding(
            "HD-SEC-001",
            "Valeurs sensibles potentiellement écrites en clair",
            "high",
            "configuration",
            f"{len(inline_secrets)} ligne(s) utilisent un nom de clé associé à un secret en dehors de secrets.yaml.",
            "Déplacer les valeurs réellement sensibles vers secrets.yaml ou vers le mécanisme sécurisé recommandé par l'intégration.",
            examples=inline_secrets[:12],
        ))

    # Long delays / mode single
    long_delay_autos = []
    single_delay_autos = []
    for auto in automations:
        max_delay = auto.get("max_delay_seconds", 0) or 0
        if max_delay >= 900:
            long_delay_autos.append({"alias": auto.get("alias"), "delay_seconds": max_delay, "source": auto.get("source")})
        if auto.get("mode", "single") == "single" and max_delay >= 300:
            single_delay_autos.append({"alias": auto.get("alias"), "delay_seconds": max_delay, "source": auto.get("source")})

    if long_delay_autos:
        findings.append(finding(
            "HD-AUTO-001",
            "Délais longs dans des automatisations",
            "low",
            "automations",
            f"{len(long_delay_autos)} automatisation(s) contiennent un délai d'au moins 15 minutes.",
            "Pour les attentes longues, vérifier qu'un redémarrage de Home Assistant ne casse pas la logique et envisager timer/helper ou trigger dédié.",
            examples=long_delay_autos[:10],
        ))

    if single_delay_autos:
        findings.append(finding(
            "HD-AUTO-002",
            "Automatisations en mode single avec attente longue",
            "medium",
            "automations",
            f"{len(single_delay_autos)} automatisation(s) sont en mode single et bloquent une nouvelle exécution pendant une attente d'au moins 5 minutes.",
            "Vérifier si les nouveaux déclenchements doivent réellement être ignorés pendant l'attente.",
            examples=single_delay_autos[:10],
        ))

    # Multiple automations controlling same entity
    controllers = defaultdict(list)
    for auto in automations:
        for entity_id in auto.get("controlled_entities", []):
            controllers[entity_id].append(auto.get("alias") or auto.get("id") or "Automation sans nom")
    conflicts = [
        {"entity_id": entity, "automations": sorted(set(names))}
        for entity, names in controllers.items()
        if len(set(names)) >= 2
    ]
    conflicts.sort(key=lambda x: (-len(x["automations"]), x["entity_id"]))
    if conflicts:
        findings.append(finding(
            "HD-AUTO-003",
            "Plusieurs automatisations pilotent les mêmes entités",
            "medium",
            "automations",
            f"{len(conflicts)} entité(s) sont commandées par au moins deux automatisations.",
            "Ce n'est pas forcément une erreur. Examiner les priorités, conditions et modes pour éviter les commandes contradictoires.",
            examples=conflicts[:15],
        ))

    disabled = [a for a in automations if a.get("enabled") is False]
    if disabled:
        findings.append(finding(
            "HD-AUTO-004",
            "Automatisations explicitement désactivées dans le YAML",
            "info",
            "automations",
            f"{len(disabled)} automatisation(s) sont marquées désactivées.",
            "Conserver si volontaire ; sinon vérifier si elles correspondent à d'anciens essais ou fonctions abandonnées.",
            examples=[{"alias": a.get("alias"), "source": a.get("source")} for a in disabled[:10]],
        ))

    # Scan limits / unreadable YAML
    skipped = yaml_analysis.get("skipped_files", [])
    parse_errors = yaml_analysis.get("parse_errors", [])
    if parse_errors:
        findings.append(finding(
            "HD-CFG-002",
            "Certains YAML n'ont pas pu être interprétés complètement",
            "low",
            "configuration",
            f"{len(parse_errors)} fichier(s) ont produit une erreur de parsing non bloquante.",
            "Vérifier ces fichiers. HA Doctor utilise aussi une analyse textuelle afin de poursuivre le diagnostic.",
            examples=parse_errors[:10],
        ))
    if skipped:
        findings.append(finding(
            "HD-CFG-003",
            "Certains fichiers ont été ignorés par limite de sécurité",
            "info",
            "configuration",
            f"{len(skipped)} fichier(s) n'ont pas été lus car ils dépassaient la taille maximale autorisée ou étaient exclus.",
            "Aucune action requise sauf si un fichier de configuration important apparaît dans cette liste.",
            examples=skipped[:10],
        ))

    return findings


def build_scores(findings):
    scores = {domain: 100 for domain in DOMAIN_LABELS}
    for item in findings:
        domain = item.get("domain")
        if domain in scores:
            scores[domain] = max(0, scores[domain] - SEVERITY_PENALTY.get(item.get("severity"), 0))

    # Automations are intentionally weighted higher: this is HA Doctor's core value.
    weights = {"system": 0.15, "entities": 0.20, "automations": 0.40, "configuration": 0.25}
    global_score = round(sum(scores[k] * weights[k] for k in scores))
    return {"global": global_score, "domains": scores}
