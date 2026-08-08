from collections import defaultdict
from itertools import combinations

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

STATELESS_UNKNOWN_DOMAINS = {"scene", "button", "event", "conversation", "stt", "tts"}
NON_CONFLICT_TARGET_DOMAINS = {"script", "scene", "button"}
NUMERIC_HELPER_DOMAINS = {"input_number", "counter"}
REFERENCE_EXCLUDED_PATH_PARTS = {"custom_components", "themes", "esphome", "zigbee2mqtt"}
ACTION_VERB_PREFIXES = (
    "turn_", "set_", "alarm_", "toggle", "press", "open_", "close_", "lock", "unlock",
    "select_", "reload", "update", "start", "stop", "pause", "play", "volume_", "media_",
    "get_", "list_", "query_", "reset", "increment", "decrement",
)


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


def _entity_domain(entity_id):
    if isinstance(entity_id, str) and "." in entity_id:
        return entity_id.split(".", 1)[0]
    return ""


def _entity_object_id(entity_id):
    if isinstance(entity_id, str) and "." in entity_id:
        return entity_id.split(".", 1)[1]
    return ""


def _mutually_exclusive(a, b):
    guards_a = a.get("state_guards", {}) or {}
    guards_b = b.get("state_guards", {}) or {}
    for entity in set(guards_a) & set(guards_b):
        states_a = set(guards_a.get(entity, []))
        states_b = set(guards_b.get(entity, []))
        if states_a and states_b and states_a.isdisjoint(states_b):
            return True
    return False


def _automation_key(auto):
    return (auto.get("id"), auto.get("alias"), auto.get("source"))


def _looks_like_action_reference(item):
    entity_id = item.get("entity_id", "") if isinstance(item, dict) else ""
    object_id = _entity_object_id(entity_id).lower()
    return object_id.startswith(ACTION_VERB_PREFIXES)


def _technical_reference_path(item):
    locations = item.get("locations", []) if isinstance(item, dict) else []
    if not locations:
        return False
    for loc in locations:
        path = str(loc.get("file", "")).replace("\\", "/").lower()
        parts = set(path.split("/"))
        if not (parts & REFERENCE_EXCLUDED_PATH_PARTS):
            return False
    return True


def _archived_secret(item):
    path = str(item.get("file", "")).replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    parts = set(path.split("/"))
    return bool(parts & {"archive", "archives", "backup", "backups"}) or "backup" in name or "archive" in name


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

    unavailable = [s for s in states if isinstance(s, dict) and s.get("state") == "unavailable"]
    unknown_raw = [s for s in states if isinstance(s, dict) and s.get("state") == "unknown"]
    unknown = [
        s for s in unknown_raw
        if _entity_domain(s.get("entity_id", "")) not in STATELESS_UNKNOWN_DOMAINS
    ]
    total = max(len(states), 1)
    unavailable_ratio = len(unavailable) / total
    unknown_ratio = len(unknown) / total

    if len(unavailable) >= 10 or unavailable_ratio >= 0.05:
        sev = "high" if unavailable_ratio >= 0.15 else "medium"
        findings.append(finding(
            "HD-ENT-001",
            "Nombre important d'entités indisponibles",
            sev,
            "entities",
            f"{len(unavailable)} entité(s) sont actuellement unavailable sur {len(states)} états.",
            "Identifier les intégrations ou appareils communs à ces entités. Les capteurs mobiles temporaires peuvent gonfler ce total, donc éviter toute suppression automatique.",
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
        sev = "medium" if len(unknown) >= 25 or unknown_ratio >= 0.03 else "low"
        findings.append(finding(
            "HD-ENT-003",
            "Entités avec un état réellement inconnu",
            sev,
            "entities",
            f"{len(unknown)} entité(s) stateful sont actuellement unknown. {len(unknown_raw) - len(unknown)} entité(s) stateless ont été ignorées.",
            "Contrôler en priorité les capteurs, nombres, sélecteurs, personnes et autres entités qui devraient normalement exposer une valeur.",
            examples=[x.get("entity_id") for x in unknown[:10]],
        ))

    raw_missing_refs = yaml_analysis.get("missing_entity_references", [])
    missing_refs = [
        item for item in raw_missing_refs
        if not _looks_like_action_reference(item) and not _technical_reference_path(item)
    ]
    if missing_refs:
        sev = "medium" if len(missing_refs) >= 10 else "low"
        findings.append(finding(
            "HD-CFG-001",
            "Références d'entités absentes détectées dans le YAML",
            sev,
            "configuration",
            f"{len(missing_refs)} référence(s) ressemblent à des entity_id mais ne figurent pas dans les états actuels. {len(raw_missing_refs) - len(missing_refs)} faux positifs techniques ont été filtrés.",
            "Vérifier ces références avant suppression. Les actions Home Assistant et les fichiers techniques connus sont ignorés autant que possible.",
            examples=missing_refs[:15],
        ))

    inline_secrets = yaml_analysis.get("potential_inline_secrets", [])
    active_secrets = [x for x in inline_secrets if not _archived_secret(x)]
    archived_secrets = [x for x in inline_secrets if _archived_secret(x)]
    if active_secrets:
        findings.append(finding(
            "HD-SEC-001",
            "Valeurs sensibles potentielles dans des configurations actives",
            "high",
            "security",
            f"{len(active_secrets)} ligne(s) actives utilisent un nom de clé associé à un secret en dehors de secrets.yaml.",
            "Déplacer les valeurs réellement sensibles vers le mécanisme de secrets de l'application concernée. Ne jamais copier leur valeur dans un rapport.",
            examples=active_secrets[:12],
        ))
    if archived_secrets:
        findings.append(finding(
            "HD-SEC-003",
            "Secrets potentiels conservés dans des archives ou sauvegardes YAML",
            "low",
            "security",
            f"{len(archived_secrets)} ligne(s) sensibles potentielles apparaissent dans des fichiers d'archive ou de sauvegarde.",
            "Supprimer les anciennes copies inutiles ou les protéger comme des secrets. Une sauvegarde oubliée peut conserver d'anciens mots de passe.",
            examples=archived_secrets[:12],
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

    live_auto_count = sum(
        1 for state in states
        if isinstance(state, dict) and str(state.get("entity_id", "")).startswith("automation.")
    )
    detected_auto_count = len(automations)
    if live_auto_count and detected_auto_count < live_auto_count:
        coverage = round(100 * detected_auto_count / live_auto_count, 1)
        findings.append(finding(
            "HD-CFG-005",
            "Couverture partielle des automatisations",
            "info",
            "configuration",
            f"HA Doctor a relié {detected_auto_count} automatisation(s) YAML à {live_auto_count} entité(s) automation actives ({coverage} %).",
            "Cette différence n'est pas forcément une erreur. Elle indique la couverture réelle du diagnostic YAML.",
        ))

    long_delay_autos = []
    single_wait_review = []
    single_wait_risky = []
    frequent_autos = []
    duplicate_action_autos = []
    feedback_autos = []

    for auto in automations:
        max_delay = auto.get("max_delay_seconds", 0) or 0
        max_wait = auto.get("max_wait_timeout_seconds", 0) or 0
        blocking = max(max_delay, max_wait)
        interval = auto.get("min_time_pattern_interval_seconds")

        if max_delay >= 900:
            long_delay_autos.append({"alias": auto.get("alias"), "delay_seconds": max_delay, "source": auto.get("source")})

        if auto.get("mode", "single") == "single" and blocking >= 300:
            example = {"alias": auto.get("alias"), "blocking_seconds": blocking, "source": auto.get("source")}
            if interval is not None:
                example["trigger_interval_seconds"] = interval
                if interval <= blocking:
                    single_wait_risky.append(example)
            else:
                single_wait_review.append(example)

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
            "Un redémarrage de Home Assistant interrompt une exécution en cours. Vérifier si perdre cette attente est acceptable ou utiliser un helper/timer persistant.",
            examples=long_delay_autos[:10],
        ))

    if single_wait_risky or single_wait_review:
        severity = "medium" if single_wait_risky else "low"
        examples = (single_wait_risky + single_wait_review)[:10]
        if single_wait_risky:
            summary = f"{len(single_wait_risky)} automatisation(s) ont un déclencheur périodique pouvant revenir avant la fin de l'attente."
        else:
            summary = f"{len(single_wait_review)} automatisation(s) utilisent mode single avec une attente longue à valider."
        findings.append(finding(
            "HD-AUTO-002",
            "Automatisations en mode single avec attente longue",
            severity,
            "automations",
            summary,
            "Le risque dépend du rythme réel des déclenchements. HA Doctor n'alerte plus lorsqu'un time_pattern connu est plus lent que l'attente.",
            examples=examples,
        ))

    numeric_writers = defaultdict(list)
    for auto in automations:
        for entity_id in auto.get("controlled_entities", []):
            if _entity_domain(entity_id) in NUMERIC_HELPER_DOMAINS:
                numeric_writers[entity_id].append(auto)

    pair_shared_numeric = defaultdict(set)
    pair_meta = {}
    for entity_id, autos in numeric_writers.items():
        unique = {_automation_key(auto): auto for auto in autos}
        for first, second in combinations(unique.values(), 2):
            if _mutually_exclusive(first, second):
                continue
            pair_key = tuple(sorted((_automation_key(first), _automation_key(second)), key=str))
            pair_shared_numeric[pair_key].add(entity_id)
            pair_meta[pair_key] = (first, second)

    duplicate_writer_pairs = []
    high_risk_numeric_entities = set()
    for pair_key, entities in pair_shared_numeric.items():
        if len(entities) < 2:
            continue
        first, second = pair_meta[pair_key]
        high_risk_numeric_entities.update(entities)
        duplicate_writer_pairs.append({
            "automations": [first.get("alias"), second.get("alias")],
            "sources": [first.get("source"), second.get("source")],
            "shared_numeric_targets": sorted(entities),
        })

    if duplicate_writer_pairs:
        findings.append(finding(
            "HD-AUTO-009",
            "Deux automatisations écrivent les mêmes compteurs numériques",
            "high",
            "automations",
            f"{len(duplicate_writer_pairs)} paire(s) d'automatisations modifient plusieurs mêmes helpers numériques.",
            "Vérifier immédiatement qu'il ne s'agit pas de deux versions concurrentes du même calcul. Deux écrivains sur des cumuls peuvent doubler ou écraser les valeurs.",
            examples=duplicate_writer_pairs[:10],
        ))

    controllers = defaultdict(list)
    for auto in automations:
        for entity_id in auto.get("controlled_entities", []):
            if _entity_domain(entity_id) in NON_CONFLICT_TARGET_DOMAINS:
                continue
            if entity_id in high_risk_numeric_entities:
                continue
            controllers[entity_id].append(auto)

    conflicts = []
    for entity, autos in controllers.items():
        unique_autos = list({_automation_key(auto): auto for auto in autos}.values())
        if len(unique_autos) < 2:
            continue
        unsafe_pairs = []
        for first, second in combinations(unique_autos, 2):
            if not _mutually_exclusive(first, second):
                unsafe_pairs.append([first.get("alias"), second.get("alias")])
        if unsafe_pairs:
            domain = _entity_domain(entity)
            conflicts.append({
                "entity_id": entity,
                "risk": "actuator" if domain in {"switch", "light", "climate", "cover", "siren", "lock", "valve"} else "helper",
                "automations": sorted({a.get("alias") for a in unique_autos}),
                "unprotected_pairs": unsafe_pairs[:6],
            })

    conflicts.sort(key=lambda x: (x["risk"] != "actuator", -len(x["automations"]), x["entity_id"]))
    if conflicts:
        has_actuator = any(x["risk"] == "actuator" for x in conflicts)
        findings.append(finding(
            "HD-AUTO-003",
            "Plusieurs automatisations peuvent piloter les mêmes entités",
            "medium" if has_actuator else "low",
            "automations",
            f"{len(conflicts)} entité(s) ont plusieurs contrôleurs sans exclusivité clairement démontrée.",
            "Les appels de scripts partagés ne sont plus considérés comme des conflits. Examiner surtout les actionneurs physiques et les helpers réellement concurrents.",
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
            "Ce schéma peut être volontaire, notamment pour une sécurité ou un asservissement. Vérifier les conditions anti-boucle.",
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
