"""HA Doctor 0.3.1 refinement layer.

Refines the customer-facing entity-health triage introduced in 0.3.0 without
changing the proven scanner/rules engine. Keeps backward-compatible fields in
reports while making the wording less alarmist and treating notify entities as
stateless for unknown-state triage.
"""

import scanner_patch as v030

VERSION = "0.3.1"

OPTIONAL_UNAVAILABLE_GROUPS = {"device_settings", "button", "updates", "image"}
OPTIONAL_UNKNOWN_GROUPS = {"device_settings", "datetime", "updates"}
TRANSIENT_UNKNOWN_GROUPS = {"mobile"}


def _count_groups(groups, keys):
    return sum(
        int(group.get("count", 0) or 0)
        for group in (groups or [])
        if group.get("key") in keys
    )


def _refine_entity_health(health):
    health = dict(health or {})

    unavailable = dict(health.get("unavailable") or {})
    unavailable_groups = [dict(group) for group in unavailable.get("groups", [])]
    unavailable_total = int(unavailable.get("total", 0) or 0)
    transient_unavailable = int(unavailable.get("likely_transient_count", 0) or 0)
    optional_unavailable = _count_groups(unavailable_groups, OPTIONAL_UNAVAILABLE_GROUPS)
    review_unavailable = max(0, unavailable_total - transient_unavailable - optional_unavailable)
    unavailable.update({
        "groups": unavailable_groups,
        "likely_optional_count": optional_unavailable,
        "review_count": review_unavailable,
        # Backward compatibility with the 0.3.0 UI/report schema.
        "attention_count": review_unavailable,
        "triage_note": "Les éléments à examiner ne sont pas nécessairement en panne : unavailable signifie que Home Assistant ne peut actuellement ni lire ni contrôler l'entité.",
    })

    unknown = dict(health.get("unknown") or {})
    unknown_groups = [dict(group) for group in unknown.get("groups", [])]

    # Notify entities are stateless from Home Assistant's perspective. 0.3.0
    # could count them as stateful unknown entities, so correct that here.
    notify_unknown = _count_groups(unknown_groups, {"notify"})
    unknown_groups = [group for group in unknown_groups if group.get("key") != "notify"]

    stateful_unknown = max(0, int(unknown.get("stateful_count", 0) or 0) - notify_unknown)
    ignored_stateless = int(unknown.get("ignored_stateless_count", 0) or 0) + notify_unknown
    optional_unknown = _count_groups(unknown_groups, OPTIONAL_UNKNOWN_GROUPS)
    transient_unknown = _count_groups(unknown_groups, TRANSIENT_UNKNOWN_GROUPS)
    review_unknown = max(0, stateful_unknown - optional_unknown - transient_unknown)

    unknown.update({
        "groups": unknown_groups,
        "stateful_count": stateful_unknown,
        "ignored_stateless_count": ignored_stateless,
        "likely_optional_count": optional_unknown,
        "likely_transient_count": transient_unknown,
        "review_count": review_unknown,
        # Backward compatibility with the 0.3.0 UI/report schema.
        "attention_count": review_unknown,
        "triage_note": "Unknown signifie que l'entité existe mais qu'aucune valeur exploitable n'est actuellement disponible ; certains domaines optionnels ou stateless sont écartés du triage.",
    })

    health["unavailable"] = unavailable
    health["unknown"] = unknown
    return health


def _sync_entity_finding_summaries(report):
    health = report.get("entity_health") or {}
    unavailable = health.get("unavailable") or {}
    unknown = health.get("unknown") or {}

    for item in report.get("findings", []):
        if item.get("rule_id") == "HD-ENT-001":
            item["recommendation"] = (
                "Commencer par les groupes marqués à examiner. Les mobiles et certains contrôles secondaires peuvent être indisponibles temporairement sans panne réelle."
            )
        elif item.get("rule_id") == "HD-ENT-003":
            item["summary"] = (
                f"{unknown.get('stateful_count', 0)} entité(s) stateful sont actuellement unknown. "
                f"{unknown.get('ignored_stateless_count', 0)} entité(s) stateless ont été ignorées."
            )
            item["recommendation"] = (
                "Examiner en priorité les capteurs et actionneurs persistants. Les paramètres optionnels, mobiles et entités stateless sont séparés autant que possible."
            )


def scan(include_yaml=True):
    report = v030.scan(include_yaml=include_yaml)
    report["version"] = VERSION
    report["entity_health"] = _refine_entity_health(report.get("entity_health"))
    _sync_entity_finding_summaries(report)

    score_meta = dict(report.get("score_meta") or {})
    score_meta["model"] = "priority_v1.1"
    score_meta["note"] = (
        "Indice de santé alpha : priorités client + triage des entités indisponibles/inconnues."
    )
    report["score_meta"] = score_meta
    return report
