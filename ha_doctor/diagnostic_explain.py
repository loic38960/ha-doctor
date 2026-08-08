"""Deterministic explanatory diagnostics for HA Doctor 0.5.

This module does not call an external AI service and does not modify Home Assistant.
It turns existing HA Doctor findings and registry health into a customer-readable
plan: likely cause, confidence, evidence, impact, ordered checks and resolution goal.
Only data already present in the redacted HA Doctor report is used.
"""

from collections import Counter, defaultdict

ENGINE_VERSION = "explain_v1"

PRIORITY_ORDER = {"action_now": 0, "verify": 1, "optimize": 2, "info": 3}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}

TRANSIENT_PLATFORMS = {"tesla_fleet", "mobile_app"}
IDLE_PRONE_PLATFORMS = {"home_connect"}
SECONDARY_PLATFORMS = {"energy", "cloud", "hacs", "hassio", "sun", "google_translate"}


RULE_PLAYBOOK = {
    "HD-AUTO-009": {
        "confidence": "high",
        "score": 0.97,
        "diagnosis": "Deux automatisations semblent écrire dans les mêmes compteurs persistants. Elles peuvent représenter deux versions concurrentes du même calcul.",
        "impact": "Les cumuls peuvent être doublés, écrasés ou évoluer de façon incohérente, ce qui fausse ensuite les tableaux de bord et les décisions d'automatisation.",
        "causes": [
            "ancienne version d'une automatisation restée active après une refonte",
            "même logique répartie dans deux packages différents",
            "deux mécanismes voulus mais sans arbitrage explicite sur les mêmes helpers",
        ],
        "checks": [
            ("Comparer les deux automatisations signalées", "Ouvrir leurs YAML et vérifier leurs déclencheurs, conditions et formules d'écriture."),
            ("Identifier le propriétaire de chaque compteur", "Pour chaque input_number partagé, déterminer quelle automatisation est censée être l'unique source de vérité."),
            ("Contrôler l'historique récent", "Vérifier si les compteurs présentent des doubles incréments, des retours en arrière ou des sauts anormaux."),
        ],
        "goal": "Une seule logique doit normalement être responsable de chaque compteur cumulatif, sauf conception explicitement coordonnée.",
        "ignore": "Seulement si les deux écritures sont intentionnelles, mutuellement exclusives et documentées.",
    },
    "HD-SEC-001": {
        "confidence": "high",
        "score": 0.95,
        "diagnosis": "Des clés portant un nom typiquement sensible sont présentes dans des fichiers de configuration actifs en dehors de secrets.yaml.",
        "impact": "Une sauvegarde, un dépôt Git ou un partage de fichier peut exposer un mot de passe ou un jeton si la valeur est réellement sensible.",
        "causes": [
            "mot de passe saisi directement dans un YAML",
            "configuration d'une application qui ne référence pas son mécanisme de secrets",
            "fichier de test devenu configuration active",
        ],
        "checks": [
            ("Ouvrir uniquement les fichiers et lignes indiqués", "Vérifier la nature de la valeur sans la copier dans un rapport ou un ticket."),
            ("Vérifier le mécanisme de secrets de l'application", "ESPHome, Zigbee2MQTT ou l'intégration concernée peut avoir son propre mécanisme sécurisé."),
            ("Contrôler l'historique Git et les sauvegardes", "Si un vrai secret a déjà été versionné ou partagé, prévoir sa rotation après correction."),
        ],
        "goal": "Aucune valeur secrète exploitable ne doit rester en clair dans une configuration active partageable.",
        "ignore": "Si la clé détectée ne contient pas réellement un secret, par exemple une valeur factice ou une référence déjà sécurisée.",
    },
    "HD-CFG-006": {
        "confidence": "high",
        "score": 0.99,
        "diagnosis": "Un capteur Integral utilise une entité non numérique comme source. L'intégration mathématique attend une valeur numérique dans le temps.",
        "impact": "Le capteur résultant peut rester unknown, produire une valeur incohérente ou ne jamais fonctionner correctement.",
        "causes": [
            "utilisation d'un switch pour mesurer une durée de fonctionnement",
            "confusion entre intégration mathématique et comptage du temps ON/OFF",
        ],
        "checks": [
            ("Vérifier la source du helper Integral", "La source doit exposer une valeur numérique exploitable."),
            ("Déterminer le besoin réel", "Pour une durée ON/OFF, comparer avec history_stats ou un capteur numérique de puissance adapté."),
            ("Vérifier les dépendances", "Rechercher les dashboards, templates et automatisations qui utilisent le capteur actuel avant de le remplacer."),
        ],
        "goal": "Le capteur de durée/énergie doit être alimenté par un type de source compatible avec le calcul attendu.",
        "ignore": "Ce diagnostic ne doit pas être ignoré si la source est réellement un switch.",
    },
    "HD-AUTO-003": {
        "confidence": "medium",
        "score": 0.72,
        "diagnosis": "Plusieurs automatisations peuvent commander la même entité et HA Doctor ne peut pas démontrer qu'elles sont toujours mutuellement exclusives.",
        "impact": "Deux logiques peuvent se contredire, provoquer des ON/OFF rapprochés ou rendre le comportement difficile à expliquer.",
        "causes": [
            "plusieurs modes fonctionnels qui partagent le même actionneur",
            "automatisations de sécurité et de confort superposées",
            "conditions d'exclusivité exprimées dans des templates que l'analyse statique ne peut pas prouver",
        ],
        "checks": [
            ("Commencer par les actionneurs physiques", "Examiner en priorité switch, climate, cover, light et autres équipements réellement commandés."),
            ("Comparer les conditions des paires signalées", "Chercher un mode, helper ou état qui garantit qu'une seule logique peut agir à la fois."),
            ("Vérifier les traces Home Assistant", "Contrôler si plusieurs automatisations se déclenchent autour du même changement d'état."),
        ],
        "goal": "Chaque actionneur partagé doit avoir une priorité ou une exclusivité compréhensible et vérifiable.",
        "ignore": "Si les contrôleurs sont volontairement superposés et protégés par des conditions que HA Doctor ne sait pas encore interpréter.",
    },
    "HD-AUTO-005": {
        "confidence": "high",
        "score": 0.96,
        "diagnosis": "Deux actions strictement identiques se suivent dans une automatisation, ce qui ressemble fortement à un copier-coller accidentel.",
        "impact": "Une notification peut être envoyée deux fois ou une commande exécutée inutilement deux fois.",
        "causes": ["copier-coller lors d'une modification", "ancienne action non supprimée après refonte"],
        "checks": [
            ("Ouvrir l'automatisation et le chemin indiqué", "Comparer les deux actions consécutives et leurs données."),
            ("Vérifier l'historique d'exécution", "Confirmer si l'effet est effectivement produit deux fois."),
        ],
        "goal": "Conserver une seule action si le doublon n'est pas explicitement voulu.",
        "ignore": "Uniquement si le double appel est volontaire et nécessaire au périphérique ou au service cible.",
    },
    "HD-ENT-001": {
        "confidence": "medium",
        "score": 0.68,
        "diagnosis": "Un volume important d'entités est actuellement unavailable, mais ce total mélange pannes réelles, terminaux intermittents et fonctions secondaires.",
        "impact": "Les automatisations qui dépendent de ces entités peuvent perdre des informations ou ne plus pouvoir commander certains équipements.",
        "causes": [
            "un ou plusieurs appareils réellement hors ligne",
            "intégration cloud ou locale temporairement indisponible",
            "capteurs mobiles ou fonctions optionnelles qui ne remontent pas en permanence",
        ],
        "checks": [
            ("Utiliser d'abord le regroupement Intégrations & appareils", "Traiter les groupes Hors ligne avant les simples entités individuelles."),
            ("Vérifier si plusieurs entités appartiennent au même appareil", "Une panne d'appareil peut expliquer des dizaines d'entités unavailable."),
            ("Écarter les fonctions transitoires", "Ne pas supprimer automatiquement les capteurs mobiles, diagnostics ou paramètres secondaires."),
        ],
        "goal": "Réduire le problème à quelques causes réelles plutôt qu'à une longue liste d'entités.",
        "ignore": "Les indisponibilités connues et temporaires peuvent être tolérées si elles n'impactent aucune automatisation importante.",
    },
    "HD-ENT-003": {
        "confidence": "medium",
        "score": 0.64,
        "diagnosis": "Des entités qui devraient normalement exposer une valeur sont actuellement unknown après filtrage des domaines stateless connus.",
        "impact": "Les templates, conditions et calculs qui attendent une valeur numérique ou un état précis peuvent devenir indéterminés.",
        "causes": [
            "appareil endormi ou donnée non publiée dans le contexte actuel",
            "template sans donnée source valide",
            "paramètre facultatif qui n'a pas encore de valeur",
        ],
        "checks": [
            ("Prioriser les capteurs persistants", "Commencer par les sensors utilisés dans des calculs, conditions ou dashboards importants."),
            ("Comparer avec la santé de l'appareil", "Si tout l'appareil est touché, traiter la cause appareil/intégration avant l'entité."),
            ("Vérifier les templates sources", "Pour une entité template, contrôler les entités d'entrée et les valeurs par défaut."),
        ],
        "goal": "Les entités utilisées par la logique métier doivent avoir une valeur déterministe quand elles sont nécessaires.",
        "ignore": "Certaines entités peuvent légitimement être unknown quand une fonction n'est pas active ou qu'un appareil dort.",
    },
    "HD-AUTO-008": {
        "confidence": "medium",
        "score": 0.66,
        "diagnosis": "Une automatisation se déclenche sur une entité qu'elle peut également modifier. Ce schéma peut créer une réexécution ou une boucle si les conditions ne l'arrêtent pas.",
        "impact": "Risque de déclenchements répétés, de commandes inutiles ou de comportement oscillant.",
        "causes": ["asservissement volontaire", "watchdog", "condition anti-boucle absente ou insuffisante"],
        "checks": [
            ("Lire le trigger et l'action sur l'entité commune", "Identifier précisément quel changement relance l'automatisation."),
            ("Chercher une condition anti-boucle", "Vérifier état cible, délai minimal, helper de verrouillage ou condition de contexte."),
            ("Consulter les traces", "Contrôler si une seule action produit plusieurs exécutions successives."),
        ],
        "goal": "La boucle de contrôle doit converger et ne pas se réarmer inutilement sur sa propre action.",
        "ignore": "Si la réactivité à sa propre entité est volontaire et protégée par une condition robuste.",
    },
    "HD-CFG-001": {
        "confidence": "medium",
        "score": 0.70,
        "diagnosis": "Des entity_id présents dans les YAML ne figurent pas dans les états Home Assistant au moment du scan, après filtrage d'une partie des faux positifs techniques.",
        "impact": "Une carte, un template ou une automatisation peut référencer une ancienne entité et échouer silencieusement ou afficher une erreur.",
        "causes": [
            "entité renommée ou supprimée",
            "ancienne configuration conservée dans un package, une scène ou un template",
            "entité chargée seulement dans certaines conditions ou intégration momentanément absente",
        ],
        "checks": [
            ("Vérifier chaque référence avec son fichier et sa ligne", "Confirmer si l'entity_id existe encore sous un autre nom."),
            ("Rechercher le nouvel identifiant", "Comparer avec l'appareil ou l'intégration correspondante dans Home Assistant."),
            ("Ne supprimer qu'après validation", "Certaines références peuvent être légitimes dans des configurations conditionnelles."),
        ],
        "goal": "Chaque référence réellement utilisée doit pointer vers une entité existante et correctement nommée.",
        "ignore": "Si la référence est volontairement dynamique ou correspond à un chargement conditionnel que l'analyse statique ne peut pas voir.",
    },
    "HD-REG-001": {
        "confidence": "high",
        "score": 0.91,
        "diagnosis": "Une entrée active du registre n'a aucun état Home Assistant correspondant. C'est un signal plus fort qu'une simple indisponibilité.",
        "impact": "Une ancienne entité peut rester dans le registre alors que son intégration ou sa configuration ne la charge plus.",
        "causes": ["ancienne entité après renommage/suppression", "configuration locale retirée", "intégration qui ne recrée plus l'entité"],
        "checks": [
            ("Rechercher l'entité dans Paramètres > Appareils et services > Entités", "Vérifier son intégration, son statut et sa date/contexte de création si disponible."),
            ("Rechercher l'entity_id dans les YAML", "Confirmer qu'aucune automatisation, scène ou dashboard n'en dépend encore."),
            ("Vérifier l'intégration propriétaire", "S'assurer que l'absence d'état n'est pas due à un problème temporaire de chargement."),
        ],
        "goal": "Décider avec preuve si l'entrée est encore utile avant toute suppression manuelle.",
        "ignore": "Si l'intégration est temporairement en échec et doit recréer l'état au prochain chargement.",
    },
    "HD-REG-002": {
        "confidence": "low",
        "score": 0.45,
        "diagnosis": "Des entités locales sans appareil associé sont unavailable. Cela peut correspondre à d'anciennes configurations, mais ce n'est pas une preuve d'orphelin.",
        "impact": "Des helpers, scripts ou automations historiques peuvent encombrer la configuration ou cacher une configuration qui ne charge plus correctement.",
        "causes": ["ancienne automatisation/helper encore enregistré", "package temporairement invalide", "script ou template dont une dépendance manque"],
        "checks": [
            ("Comparer le nom avec les configurations actuelles", "Repérer les suffixes, anciennes versions et noms historiques évidents."),
            ("Rechercher l'entité dans les YAML", "Vérifier si elle est encore définie et utilisée."),
            ("Contrôler le journal Home Assistant", "Une erreur de chargement peut rendre une entité locale unavailable sans qu'elle soit obsolète."),
        ],
        "goal": "Classer chaque candidat en encore utilisé, temporairement cassé ou réellement ancien.",
        "ignore": "Ne jamais supprimer uniquement sur ce signal : il est volontairement de faible confiance.",
    },
    "HD-AUTO-001": {
        "confidence": "high",
        "score": 0.90,
        "diagnosis": "Une automatisation contient une attente longue. Une exécution en cours n'est pas un stockage persistant de l'intention métier.",
        "impact": "Un redémarrage ou un rechargement peut interrompre l'attente avant l'action suivante.",
        "causes": ["delay utilisé comme minuteur métier", "logique historique simple devenue critique avec le temps"],
        "checks": [
            ("Vérifier ce qui doit se passer après le délai", "Déterminer si perdre cette action après un redémarrage est acceptable."),
            ("Évaluer un helper timer ou un timestamp", "Pour une échéance importante, préférer un état persistant et reconstituable."),
        ],
        "goal": "Les attentes longues importantes doivent survivre ou être recalculables après un redémarrage.",
        "ignore": "Si l'action retardée est purement informative et peut être perdue sans conséquence.",
    },
    "HD-AUTO-002": {
        "confidence": "medium",
        "score": 0.73,
        "diagnosis": "Une automatisation en mode single reste occupée pendant une attente longue et peut ignorer de nouveaux déclenchements pendant cette période.",
        "impact": "Un événement pertinent peut être perdu si l'automatisation est encore en cours.",
        "causes": ["mode single choisi par défaut", "nouveaux triggers plus fréquents que prévu"],
        "checks": [
            ("Comparer la durée d'attente à la fréquence des triggers", "Vérifier si un nouveau trigger peut raisonnablement arriver avant la fin."),
            ("Comparer les modes restart/queued/parallel", "Choisir uniquement après avoir vérifié l'effet fonctionnel de plusieurs exécutions."),
        ],
        "goal": "Le mode d'exécution doit correspondre au comportement attendu quand plusieurs événements surviennent.",
        "ignore": "Si ignorer volontairement tout nouveau déclenchement pendant l'attente est le comportement voulu.",
    },
    "HD-SEC-003": {
        "confidence": "medium",
        "score": 0.76,
        "diagnosis": "Des fichiers d'archive ou de sauvegarde YAML semblent encore contenir des clés potentiellement sensibles.",
        "impact": "Même inutilisé, un ancien fichier peut conserver un mot de passe qui finit dans une sauvegarde ou un partage.",
        "causes": ["copies manuelles de configuration", "anciens backups conservés dans /config", "archives avant migration"],
        "checks": [
            ("Identifier les archives encore nécessaires", "Supprimer manuellement uniquement celles dont la conservation n'est plus utile."),
            ("Vérifier si les secrets sont encore valides", "Si un ancien secret a été largement copié, envisager sa rotation."),
        ],
        "goal": "Ne conserver dans /config que les archives réellement nécessaires et protégées.",
        "ignore": "Si les fichiers sont volontairement conservés, protégés et ne contiennent aucune valeur sensible réelle.",
    },
    "HD-CFG-005": {
        "confidence": "high",
        "score": 0.94,
        "diagnosis": "Le moteur YAML ne relie pas toutes les entités automation actives à une définition analysable. Il s'agit d'une mesure de couverture, pas d'une panne.",
        "impact": "Certaines automatisations peuvent ne pas bénéficier de tous les contrôles statiques HA Doctor.",
        "causes": ["automatisations créées autrement que dans les YAML scannés", "sources non couvertes ou générées dynamiquement"],
        "checks": [("Comparer le nombre d'automatisations analysées", "Utiliser cette information pour mesurer la couverture du rapport, sans corriger quoi que ce soit automatiquement.")],
        "goal": "Comprendre la limite de couverture du scan.",
        "ignore": "Cette information est sans action si la couverture restante est connue et acceptable.",
    },
}


def _confidence_label(value):
    return {"high": "Élevée", "medium": "Moyenne", "low": "Faible"}.get(value, "Moyenne")


def _priority_label(value):
    return {
        "action_now": "À corriger maintenant",
        "verify": "À vérifier",
        "optimize": "Optimisation",
        "info": "Information",
    }.get(value, "À vérifier")


def _health_label(score):
    try:
        score = int(score)
    except (TypeError, ValueError):
        return "État non calculé"
    if score >= 92:
        return "Excellent"
    if score >= 82:
        return "Bon"
    if score >= 70:
        return "À surveiller"
    if score >= 55:
        return "À corriger"
    return "Critique"


def _compact_evidence(finding_item):
    """Return evidence metadata without copying arbitrary raw values."""
    evidence = []
    summary = finding_item.get("summary")
    if summary:
        evidence.append({"type": "summary", "label": "Constat", "text": str(summary)})

    examples = finding_item.get("examples") or []
    for example in examples[:5]:
        if isinstance(example, str):
            evidence.append({"type": "entity", "label": "Entité", "text": example})
            continue
        if not isinstance(example, dict):
            continue
        if example.get("file"):
            text = str(example.get("file"))
            if example.get("line"):
                text += f":{example.get('line')}"
            if example.get("key"):
                text += f" · clé {example.get('key')}"
            evidence.append({"type": "file", "label": "Fichier", "text": text})
            continue
        if example.get("entity_id"):
            evidence.append({"type": "entity", "label": "Entité", "text": str(example.get("entity_id"))})
            continue
        automations = example.get("automations") or []
        if automations:
            evidence.append({"type": "automation", "label": "Automatisations", "text": " ↔ ".join(str(x) for x in automations[:3])})
            continue
        alias = example.get("alias")
        source = example.get("source")
        if alias or source:
            evidence.append({"type": "automation", "label": "Automatisation", "text": " · ".join(str(x) for x in (alias, source) if x)})
    return evidence[:6]


def _generic_playbook(finding_item):
    severity = finding_item.get("severity", "medium")
    confidence = "medium" if severity in {"critical", "high", "medium"} else "low"
    return {
        "confidence": confidence,
        "score": 0.60 if confidence == "medium" else 0.42,
        "diagnosis": str(finding_item.get("summary") or finding_item.get("title") or "Point détecté par HA Doctor."),
        "impact": "Ce point mérite d'être vérifié dans son contexte avant toute modification.",
        "causes": ["configuration volontaire", "ancienne configuration", "état temporaire de Home Assistant"],
        "checks": [
            ("Vérifier les exemples fournis", "Confirmer que le constat correspond encore à la configuration active."),
            ("Contrôler les dépendances", "Identifier les automatisations, dashboards ou appareils qui utilisent les éléments concernés."),
        ],
        "goal": "Confirmer la cause avant de modifier la configuration.",
        "ignore": "Si le comportement est intentionnel, documenté et sans impact fonctionnel.",
    }


def explain_finding(finding_item):
    rule_id = str(finding_item.get("rule_id") or "UNKNOWN")
    guide = RULE_PLAYBOOK.get(rule_id) or _generic_playbook(finding_item)
    checks = [
        {"step": index + 1, "title": title, "detail": detail}
        for index, (title, detail) in enumerate(guide.get("checks") or [])
    ]
    confidence = guide.get("confidence", "medium")
    return {
        "id": f"DX-{rule_id}",
        "source_type": "finding",
        "source_id": rule_id,
        "rule_id": rule_id,
        "title": finding_item.get("title") or rule_id,
        "priority": finding_item.get("priority") or "verify",
        "priority_label": finding_item.get("priority_label") or _priority_label(finding_item.get("priority")),
        "severity": finding_item.get("severity") or "medium",
        "domain": finding_item.get("domain") or "configuration",
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "confidence_score": float(guide.get("score", 0.6)),
        "diagnosis": guide.get("diagnosis"),
        "impact": guide.get("impact"),
        "probable_causes": list(guide.get("causes") or []),
        "evidence": _compact_evidence(finding_item),
        "checks": checks,
        "resolution_goal": guide.get("goal"),
        "safe_to_ignore_when": guide.get("ignore"),
        "automatic_fix": False,
        "read_only": True,
    }


def _platform_status_map(registry):
    return {
        str(item.get("integration")): item
        for item in ((registry.get("integration_health") or {}).get("groups") or [])
        if item.get("integration")
    }


def _offline_devices_by_platform(registry):
    result = defaultdict(list)
    for item in ((registry.get("device_health") or {}).get("groups") or []):
        if item.get("status") != "offline":
            continue
        platforms = item.get("platforms") or []
        for platform in platforms:
            result[str(platform)].append(item)
    return result


def _registry_evidence(item, kind):
    evidence = []
    if kind == "integration":
        evidence.append({"type": "integration", "label": "Intégration", "text": str(item.get("integration") or "inconnue")})
    else:
        evidence.append({"type": "device", "label": "Appareil", "text": str(item.get("name") or "sans nom")})
        detail = " · ".join(str(x) for x in (item.get("manufacturer"), item.get("model")) if x)
        if detail:
            evidence.append({"type": "device_meta", "label": "Matériel", "text": detail})
    evidence.append({
        "type": "ratio",
        "label": "Entités principales",
        "text": f"{int(item.get('core_affected', 0) or 0)}/{int(item.get('core_total', 0) or 0)} touchées",
    })
    states = []
    for key, label in (("unavailable", "unavailable"), ("unknown", "unknown"), ("missing_state", "sans état")):
        value = int(item.get(key, 0) or 0)
        if value:
            states.append(f"{value} {label}")
    if states:
        evidence.append({"type": "states", "label": "États", "text": " · ".join(states)})
    examples = item.get("examples") or []
    if examples:
        evidence.append({"type": "entities", "label": "Exemples", "text": " · ".join(str(x) for x in examples[:3])})
    return evidence[:6]


def _integration_incident(item, offline_devices):
    platform = str(item.get("integration") or "unknown")
    status = item.get("status")
    if platform in TRANSIENT_PLATFORMS or item.get("transient_or_sleep_tolerant"):
        return None
    if platform in SECONDARY_PLATFORMS or status == "secondary":
        return None

    core_total = int(item.get("core_total", 0) or 0)
    core_affected = int(item.get("core_affected", 0) or 0)
    healthy = int(item.get("healthy", 0) or 0)
    missing = int(item.get("missing_state", 0) or 0)
    ratio = float(item.get("affected_ratio", 0) or 0)

    if status == "offline":
        confidence = "high" if core_total >= 3 and healthy == 0 else "medium"
        score = 0.92 if confidence == "high" else 0.78
        title = f"{platform} semble indisponible"
        diagnosis = (
            f"L'intégration {platform} concentre {core_affected}/{core_total} entités principales touchées. "
            "Le regroupement suggère une cause commune au niveau de l'intégration plutôt que des pannes indépendantes de chaque entité."
        )
        causes = [
            "intégration non connectée, authentification expirée ou service cloud indisponible",
            "passerelle ou dépendance commune hors ligne",
            "plusieurs appareils de la même intégration devenus indisponibles en même temps",
        ]
        checks = [
            ("Ouvrir Paramètres > Appareils et services", f"Vérifier l'état de l'intégration {platform} et la présence d'un message de reconfiguration ou d'authentification."),
            ("Comparer plusieurs appareils de cette intégration", "Si des appareils indépendants sont tous touchés, privilégier la cause intégration/passerelle."),
            ("Consulter les journaux liés à l'intégration", "Rechercher les erreurs de connexion, authentification, timeout ou API."),
        ]
        goal = "Rétablir l'intégration commune avant de traiter les entités une par une."
    elif status == "degraded" and core_affected >= 4 and ratio >= 0.25:
        confidence = "medium"
        score = 0.74
        title = f"{platform} est partiellement dégradée"
        if platform in IDLE_PRONE_PLATFORMS:
            diagnosis = (
                f"{core_affected}/{core_total} entités principales de {platform} n'ont pas de valeur exploitable. "
                "Cette intégration peut toutefois exposer des états seulement pendant certains programmes ou lorsque l'appareil est actif."
            )
            score = 0.61
        else:
            diagnosis = (
                f"{core_affected}/{core_total} entités principales de {platform} sont touchées tandis que d'autres restent saines. "
                "Cela oriente vers une panne partielle, un sous-ensemble d'appareils ou des fonctions non disponibles."
            )
        causes = [
            "un sous-ensemble d'appareils hors ligne",
            "fonctionnalités non disponibles dans l'état actuel des appareils",
            "problème partiel de communication ou de synchronisation",
        ]
        checks = [
            ("Identifier les appareils réellement touchés", "Utiliser le bloc Appareils pour voir si les anomalies se concentrent sur quelques équipements."),
            ("Comparer avec un appareil sain de la même intégration", "Cela permet de distinguer une panne d'intégration d'une panne d'équipement."),
            ("Vérifier le contexte d'utilisation", "Pour les appareils électroménagers ou véhicules, certaines valeurs peuvent être absentes lorsqu'ils sont inactifs."),
        ]
        goal = "Isoler si l'anomalie vient de l'intégration, d'un appareil précis ou d'une fonction optionnelle."
    else:
        return None

    device_names = [str(x.get("name") or "Appareil") for x in offline_devices[:4]]
    if device_names:
        diagnosis += " Appareils entièrement touchés détectés : " + ", ".join(device_names) + "."

    return {
        "id": f"DX-REG-INT-{platform}",
        "source_type": "registry_integration",
        "source_id": platform,
        "title": title,
        "priority": "verify",
        "priority_label": "À vérifier",
        "severity": "medium" if status == "offline" else "low",
        "domain": "entities",
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "confidence_score": score,
        "diagnosis": diagnosis,
        "impact": "Les équipements et automatisations dépendant de cette intégration peuvent perdre leurs états ou commandes jusqu'au rétablissement.",
        "probable_causes": causes,
        "evidence": _registry_evidence(item, "integration"),
        "checks": [{"step": i + 1, "title": t, "detail": d} for i, (t, d) in enumerate(checks)],
        "resolution_goal": goal,
        "safe_to_ignore_when": "Si les appareils concernés sont volontairement éteints/inactifs et que l'intégration ne signale aucune erreur réelle.",
        "automatic_fix": False,
        "read_only": True,
        "registry_status": status,
    }


def _multi_device_cluster(platform, integration, devices):
    if len(devices) < 2 or platform in TRANSIENT_PLATFORMS:
        return None
    names = [str(x.get("name") or "Appareil") for x in devices[:6]]
    count = len(devices)
    integration_status = (integration or {}).get("status")
    if integration_status == "offline":
        return None  # already represented by integration incident

    confidence = "high" if count >= 3 else "medium"
    score = 0.88 if confidence == "high" else 0.76
    return {
        "id": f"DX-REG-CLUSTER-{platform}",
        "source_type": "registry_cluster",
        "source_id": platform,
        "title": f"{count} appareils {platform} sont entièrement indisponibles",
        "priority": "verify",
        "priority_label": "À vérifier",
        "severity": "medium",
        "domain": "entities",
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "confidence_score": score,
        "diagnosis": (
            f"HA Doctor voit plusieurs appareils distincts de {platform} avec 100 % de leurs entités principales touchées : "
            + ", ".join(names)
            + ". Une cause commune à ce sous-ensemble est plus plausible que des erreurs indépendantes dans chaque entité."
        ),
        "impact": "Les fonctions pilotées par ces appareils peuvent être indisponibles même si le reste de l'intégration continue de fonctionner.",
        "probable_causes": [
            "passerelle, zone réseau ou protocole commun au sous-ensemble",
            "appareils volontairement hors tension ou déconnectés",
            "ancienne association d'appareils conservée après remplacement",
        ],
        "evidence": [
            {"type": "integration", "label": "Intégration", "text": platform},
            {"type": "devices", "label": "Appareils hors ligne", "text": ", ".join(names)},
        ],
        "checks": [
            {"step": 1, "title": "Vérifier un appareil physique", "detail": "Choisir un des appareils listés et confirmer alimentation, connectivité et disponibilité dans l'application constructeur."},
            {"step": 2, "title": "Chercher leur point commun", "detail": "Comparer passerelle, zone radio, réseau, compte cloud ou période de remplacement."},
            {"step": 3, "title": "Comparer avec un appareil sain de la même intégration", "detail": "Si d'autres équipements de la même intégration fonctionnent, l'intégration globale n'est probablement pas la cause principale."},
        ],
        "resolution_goal": "Identifier la dépendance commune aux appareils hors ligne sans toucher aux équipements sains.",
        "safe_to_ignore_when": "Si tous ces appareils sont volontairement coupés ou saisonniers.",
        "automatic_fix": False,
        "read_only": True,
        "registry_status": "offline_cluster",
    }


def _device_incident(item, platform_statuses, clustered_platforms):
    if item.get("status") != "offline":
        return None
    platforms = [str(x) for x in (item.get("platforms") or [])]
    platform = platforms[0] if platforms else "unknown"
    if platform in TRANSIENT_PLATFORMS or platform in clustered_platforms:
        return None
    integration = platform_statuses.get(platform) or {}
    if integration.get("status") == "offline":
        return None

    core_total = int(item.get("core_total", 0) or 0)
    core_affected = int(item.get("core_affected", 0) or 0)
    if core_total <= 0 or core_affected < core_total:
        return None

    confidence = "high" if core_total >= 3 else "medium"
    score = 0.88 if confidence == "high" else 0.72
    name = str(item.get("name") or "Appareil")
    if platform == "mqtt":
        causes = [
            "appareil hors tension ou hors portée",
            "availability topic indiquant offline",
            "MQTT discovery non republié après redémarrage ou message retained obsolète",
        ]
        first = "Vérifier l'alimentation, la liaison Zigbee/Wi-Fi et l'état du périphérique dans Zigbee2MQTT ou l'outil MQTT concerné."
    else:
        causes = ["appareil hors tension", "connexion réseau/radio perdue", "appareil retiré ou remplacé mais toujours enregistré"]
        first = "Confirmer que l'appareil est alimenté et joignable dans l'application ou la passerelle qui le gère."

    return {
        "id": f"DX-REG-DEV-{platform}-{name}",
        "source_type": "registry_device",
        "source_id": name,
        "title": f"{name} semble hors ligne",
        "priority": "verify",
        "priority_label": "À vérifier",
        "severity": "medium",
        "domain": "entities",
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "confidence_score": score,
        "diagnosis": f"Toutes les entités principales observées pour {name} sont touchées ({core_affected}/{core_total}), alors que l'intégration {platform} n'est pas entièrement hors ligne.",
        "impact": "Les automatisations et commandes dépendant directement de cet appareil peuvent ne plus fonctionner.",
        "probable_causes": causes,
        "evidence": _registry_evidence(item, "device"),
        "checks": [
            {"step": 1, "title": "Vérifier l'appareil lui-même", "detail": first},
            {"step": 2, "title": "Comparer avec l'intégration", "detail": f"Vérifier qu'un autre appareil {platform} fonctionne encore, ce qui confirmerait une panne localisée."},
            {"step": 3, "title": "Vérifier les dépendances HA", "detail": "Rechercher les automatisations critiques qui utilisent cet appareil avant toute suppression ou réappairage."},
        ],
        "resolution_goal": "Rétablir ou confirmer le retrait de l'appareil avant de nettoyer ses entités.",
        "safe_to_ignore_when": "Si l'appareil est volontairement débranché, saisonnier ou retiré mais conservé temporairement.",
        "automatic_fix": False,
        "read_only": True,
        "registry_status": "offline",
    }


def explain_registry(registry):
    if not registry or not registry.get("available"):
        return [], []

    platform_statuses = _platform_status_map(registry)
    offline_by_platform = _offline_devices_by_platform(registry)
    incidents = []
    observations = []

    for platform, item in platform_statuses.items():
        if platform in TRANSIENT_PLATFORMS or item.get("transient_or_sleep_tolerant"):
            observations.append({
                "type": "expected_transient",
                "integration": platform,
                "message": item.get("status_note") or "Indisponibilités potentiellement transitoires ; aucune panne conclue automatiquement.",
                "core_affected": item.get("core_affected", 0),
                "core_total": item.get("core_total", 0),
            })
            continue
        incident = _integration_incident(item, offline_by_platform.get(platform, []))
        if incident:
            incidents.append(incident)

    clustered_platforms = set()
    for platform, devices in offline_by_platform.items():
        cluster = _multi_device_cluster(platform, platform_statuses.get(platform), devices)
        if cluster:
            incidents.append(cluster)
            clustered_platforms.add(platform)

    for item in ((registry.get("device_health") or {}).get("groups") or []):
        incident = _device_incident(item, platform_statuses, clustered_platforms)
        if incident:
            incidents.append(incident)

    incidents.sort(key=lambda x: (
        PRIORITY_ORDER.get(x.get("priority"), 9),
        CONFIDENCE_ORDER.get(x.get("confidence"), 9),
        -float(x.get("confidence_score", 0) or 0),
        x.get("title", ""),
    ))
    return incidents[:12], observations[:12]


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
    }


def build_action_plan(explanations):
    actionable = [x for x in explanations if x.get("priority") in {"action_now", "verify", "optimize"}]
    actionable.sort(key=lambda x: (
        PRIORITY_ORDER.get(x.get("priority"), 9),
        SEVERITY_ORDER.get(x.get("severity"), 9),
        CONFIDENCE_ORDER.get(x.get("confidence"), 9),
        -float(x.get("confidence_score", 0) or 0),
        x.get("title", ""),
    ))
    items = [_action_item(x) for x in actionable[:12]]
    counts = Counter(x.get("priority") for x in actionable)
    return {
        "total": len(actionable),
        "counts": {
            "action_now": counts.get("action_now", 0),
            "verify": counts.get("verify", 0),
            "optimize": counts.get("optimize", 0),
        },
        "items": items,
        "top": items[:5],
        "note": "Plan déterministe et en lecture seule : aucune étape n'est exécutée automatiquement par HA Doctor.",
    }


def build_executive_summary(report, explanations, registry_observations):
    scores = report.get("scores") or {}
    global_score = scores.get("global")
    summary = report.get("diagnostic_summary") or {}
    priority = summary.get("priority_counts") or {}
    registry = report.get("registry_analysis") or {}
    ih = registry.get("integration_health") or {}
    dh = registry.get("device_health") or {}

    top = [x for x in explanations if x.get("priority") == "action_now"][:3]
    top_titles = [str(x.get("title")) for x in top if x.get("title")]
    sentences = [f"Indice de santé {global_score}/100 ({_health_label(global_score)})."] if global_score is not None else []
    sentences.append(
        f"{int(priority.get('action_now', 0) or 0)} correction(s) prioritaire(s), "
        f"{int(priority.get('verify', 0) or 0)} point(s) à vérifier et "
        f"{int(priority.get('optimize', 0) or 0)} optimisation(s) dans le moteur de règles."
    )
    if registry.get("available"):
        sentences.append(
            f"Le registre regroupe les anomalies en {int(ih.get('problematic', 0) or 0)} intégration(s) réellement problématique(s) "
            f"et {int(dh.get('problematic', 0) or 0)} appareil(s) réellement problématique(s), sans compter les simples états transitoires."
        )
    if top_titles:
        sentences.append("Priorités actuelles : " + " ; ".join(top_titles) + ".")
    if registry_observations:
        names = [str(x.get("integration")) for x in registry_observations[:3] if x.get("integration")]
        if names:
            sentences.append("HA Doctor a volontairement classé comme potentiellement transitoires : " + ", ".join(names) + ".")

    return {
        "health_score": global_score,
        "health_label": _health_label(global_score),
        "text": " ".join(sentences),
        "top_priority_titles": top_titles,
        "registry_available": bool(registry.get("available")),
    }


def enrich_report(report):
    """Add 0.5 explanatory diagnostics without changing the health score."""
    finding_explanations = [explain_finding(item) for item in (report.get("findings") or [])]
    registry_incidents, registry_observations = explain_registry(report.get("registry_analysis") or {})
    explanations = finding_explanations + registry_incidents
    explanations.sort(key=lambda x: (
        PRIORITY_ORDER.get(x.get("priority"), 9),
        SEVERITY_ORDER.get(x.get("severity"), 9),
        CONFIDENCE_ORDER.get(x.get("confidence"), 9),
        -float(x.get("confidence_score", 0) or 0),
        x.get("title", ""),
    ))

    action_plan = build_action_plan(explanations)
    report["diagnostic_engine"] = {
        "version": ENGINE_VERSION,
        "mode": "deterministic_local",
        "external_ai_used": False,
        "automatic_fix": False,
        "read_only": True,
        "explanation_count": len(explanations),
        "finding_explanation_count": len(finding_explanations),
        "registry_incident_count": len(registry_incidents),
        "confidence_counts": dict(Counter(x.get("confidence") for x in explanations)),
    }
    report["executive_summary"] = build_executive_summary(report, explanations, registry_observations)
    report["action_plan"] = action_plan
    report["diagnostic_explanations"] = explanations[:40]
    report["registry_observations"] = registry_observations
    report.setdefault("privacy", {})["explanatory_engine_external_ai_used"] = False
    report["privacy"]["explanatory_engine_raw_state_values_persisted"] = False
    return report
