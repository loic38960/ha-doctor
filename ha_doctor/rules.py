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
    "security": "Sécurité",
    "performance": "Performances",
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


def _mutually_exclusive(a, b):
    guards_a = a.get("state_guards", {}) or {}
    guards_b = b.get("state_guards", {}) or {}
    for entity in set(guards_a) & set(guards_b):
        states_a = set(guards_a.get(entity, []))
        states_b = set(guards_b.get(entity, []))
        if states_a and states_b and states_a.isdisjoint(states_b):
            return True
    return False


def evaluate(snapshot):
    findings = []
    states = snapshot.get("states", [])
    yaml_analysis = snapshot.get("yaml", {})
    automations = yaml_analysis.get("automations", [])
    config_summary = yaml_analysis.get("configuration", {}) or {}

    if snapshot.get("api_errors"):
        findings.append(finding(
            "HD-SYS-001",
            "Certaines informations système sont inaccessibles",
            "low",
            "system",
            f"{len(snapshot['api_errors'])} appel(s) d'information n'ont pas répondu correctement.",
            "Vérifier les journaux HA Doctor. Le scan principal continue même si une API secondaire n'est pas disponible.",
        ))

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

    missing_refs = yaml_analysis.get("missing_entity_references", [])
    if missing_refs:
        sev = "medium" if len(missing_refs) >= 5 else "low"
        findings.append(finding(
            "HD-CFG-001",
            "Références d'entités absentes détectées dans le YAML",
            sev,
            "configuration",
            f"{len(missing_refs)} référence(s) pointent vers des entity_id qui ne figurent pas dans les états actuels.",
            "Vérifier les références avant suppression : certains templates ou chargements tardifs peuvent produire des faux positifs.",
            examples=missing_refs[:15],
        ))

    inline_secrets = yaml_analysis.get("potential_inline_secrets", [])
    if inline_secrets:
        findings.append(finding(
            "HD-SEC-001",
            "Valeurs sensibles potentiellement écrites en clair",
            "high",
            "security",
            f"{len(inline_secrets)} ligne(s) utilisent un nom de clé associé à un secret en dehors de secrets.yaml.",
            "Déplacer les valeurs réellement sensibles vers secrets.yaml ou vers le mécanisme sécurisé recommandé par l'intégration.",
            examples=inline_secrets[:12],
        ))

    if config_summary.get("trusted_proxy_all_network"):
        findings.append(finding(
            "HD-SEC-002",
            "Réseau entier autorisé comme proxy de confiance",
            "high",
            "security",
            "La configuration HTTP semble autoriser une plage /0 dans trusted_proxies.",
            "Limiter trusted_proxies aux adresses ou sous-réseaux réellement utilisés par le reverse proxy.",
        ))

    unresolved = yaml_analysis.get("unresolved_blueprints", [])
    if unresolved:
        findings.append(finding(
            "HD-CFG-004",
            "Blueprints utilisés mais non résolus",
            "medium",
            "configuration",
            f"{len(unresolved)} automatisation(s) utilisent un blueprint que HA Doctor n'a pas pu charger.",
            "Vérifier que les fichiers de blueprint sont présents dans /config/blueprints/automation. L'analyse de ces automatisations est partielle.",
            examples=unresolved[:12],
        ))

    long_delay_autos = []
    single_wait_autos = []
    frequent_autos = []
    duplicate_action_autos = []
    feedback_autos = []
    for auto in automations:
        max_delay = auto.get("max_delay_seconds", 0) or 0
        max_wait = auto.get("max_wait_timeout_seconds", 0) or 0
        blocking = max(max_delay, max_wait)
        if max_delay >= 900:
            long_delay_autos.append({"alias": auto.get("alias"), "delay_seconds": max_delay, "source": auto.get("source")})
        if auto.get("mode", "single") == "single" and blocking >= 300:
            single_wait_autos.append({"alias": auto.get("alias"), "blocking_seconds": blocking, "source": auto.get("source")})
        interval = auto.get("min_time_pattern_interval_seconds")
        if interval is not None and interval < 10:
            frequent_autos.append({"alias": auto.get("alias"), "interval_seconds": interval, "source": auto.get("source")})
        if auto.get("consecutive_duplicate_actions"):
            duplicate_action_autos.append({
                "alias": auto.get("alias"),
                "source": auto.get("source"),
                "duplicates": auto.get("consecutive_duplicate_actions")[:5],
            })
        overlap = sorted(set(auto.get("trigger_entities", [])) & set(auto.get("controlled_entities", [])))
        if overlap:
            feedback_autos.append({"alias": auto.get("alias"), "source": auto.get("source"), "entities": overlap})

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

    if single_wait_autos:
        findings.append(finding(
            "HD-AUTO-002",
            "Automatisations en mode single avec attente longue",
            "medium",
            "automations",
            f"{len(single_wait_autos)} automatisation(s) peuvent ignorer de nouveaux déclenchements pendant au moins 5 minutes.",
            "Vérifier si les nouveaux déclenchements doivent réellement être ignorés pendant l'attente.",
            examples=single_wait_autos[:10],
        ))

    controllers = defaultdict(list)
    for auto in automations:
        for entity_id in auto.get("controlled_entities", []):
            controllers[entity_id].append(auto)
    conflicts = []
    for entity, autos in controllers.items():
        unique = []
        seen_names = set()
        for auto in autos:
            key = (auto.get("id"), auto.get("alias"), auto.get("source"))
            if key not in seen_names:
                seen_names.add(key)
                unique.append(auto)
        if len(unique) < 2:
            continue
        unsafe_pairs = []
        for idx, first in enumerate(unique):
            for second in unique[idx + 1:]:
                if not _mutually_exclusive(first, second):
                    unsafe_pairs.append([first.get("alias"), second.get("alias")])
        if unsafe_pairs:
            conflicts.append({
                "entity_id": entity,
                "automations": sorted({a.get("alias") for a in unique}),
                "unprotected_pairs": unsafe_pairs[:6],
            })
    conflicts.sort(key=lambda x: (-len(x["automations"]), x["entity_id"]))
    if conflicts:
        findings.append(finding(
            "HD-AUTO-003",
            "Plusieurs automatisations peuvent piloter les mêmes entités",
            "medium",
            "automations",
            f"{len(conflicts)} entité(s) ont plusieurs contrôleurs sans exclusivité clairement démontrée.",
            "Examiner les priorités, conditions et modes. HA Doctor ignore désormais les contrôleurs séparés par des conditions d'état mutuellement exclusives.",
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

    if duplicate_action_autos:
        findings.append(finding(
            "HD-AUTO-005",
            "Actions consécutives identiques",
            "medium",
            "automations",
            f"{len(duplicate_action_autos)} automatisation(s) contiennent deux actions strictement identiques l'une à la suite de l'autre.",
            "Vérifier si le doublon est volontaire. Pour une notification ou une commande, c'est souvent un copier-coller accidentel.",
            examples=duplicate_action_autos[:10],
        ))

    ids = defaultdict(list)
    aliases = defaultdict(list)
    for auto in automations:
        if auto.get("id"):
            ids[str(auto["id"])].append(auto)
        alias = (auto.get("alias") or "").strip()
        if alias:
            aliases[alias].append(auto)

    duplicate_ids = [
        {"id": key, "automations": [{"alias": a.get("alias"), "source": a.get("source")} for a in vals]}
        for key, vals in ids.items() if len(vals) > 1
    ]
    if duplicate_ids:
        findings.append(finding(
            "HD-AUTO-006",
            "Identifiants d'automatisation dupliqués",
            "high",
            "automations",
            f"{len(duplicate_ids)} identifiant(s) d'automatisation sont utilisés plusieurs fois.",
            "Donner un id unique à chaque automatisation afin d'éviter les collisions et comportements difficiles à diagnostiquer.",
            examples=duplicate_ids[:10],
        ))

    duplicate_aliases = [
        {"alias": key, "sources": sorted({a.get("source") for a in vals})}
        for key, vals in aliases.items() if len(vals) > 1
    ]
    if duplicate_aliases:
        findings.append(finding(
            "HD-AUTO-007",
            "Noms d'automatisations dupliqués",
            "low",
            "automations",
            f"{len(duplicate_aliases)} alias sont utilisés par plusieurs automatisations.",
            "Utiliser des noms uniques facilite les traces, les notifications et le diagnostic.",
            examples=duplicate_aliases[:10],
        ))

    if feedback_autos:
        findings.append(finding(
            "HD-AUTO-008",
            "Automatisations déclenchées par une entité qu'elles commandent aussi",
            "low",
            "automations",
            f"{len(feedback_autos)} automatisation(s) réagissent à une entité qu'elles peuvent également modifier.",
            "Ce schéma peut être volontaire, mais vérifier les conditions afin d'éviter une boucle ou des réexécutions inutiles.",
            examples=feedback_autos[:10],
        ))

    if frequent_autos:
        findings.append(finding(
            "HD-PERF-001",
            "Déclencheurs time_pattern très fréquents",
            "medium",
            "performance",
            f"{len(frequent_autos)} automatisation(s) peuvent s'exécuter plus d'une fois toutes les 10 secondes.",
            "Réduire la fréquence si une réaction événementielle ou une période plus longue suffit.",
            examples=frequent_autos[:10],
        ))

    purge_days = config_summary.get("recorder_purge_keep_days")
    if isinstance(purge_days, (int, float)) and purge_days > 30:
        findings.append(finding(
            "HD-PERF-002",
            "Rétention Recorder élevée",
            "medium" if purge_days > 90 else "low",
            "performance",
            f"Recorder conserve actuellement {purge_days:g} jours d'historique.",
            "Vérifier que cette durée est nécessaire, surtout si la base de données grossit rapidement.",
        ))

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

    weights = {
        "system": 0.10,
        "entities": 0.15,
        "automations": 0.35,
        "configuration": 0.15,
        "security": 0.15,
        "performance": 0.10,
    }
    global_score = round(sum(scores[k] * weights[k] for k in scores))
    return {"global": global_score, "domains": scores}
