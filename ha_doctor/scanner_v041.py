"""HA Doctor 0.4.1 registry calibration layer.

Keeps the 0.4.0 registry collection intact but calibrates interpretation:
- sleep/transient-heavy platforms such as Tesla Fleet and Mobile App are not
  labelled offline solely because many values are temporarily unknown/unavailable;
- medium-confidence local unavailable entities are separated from true orphan
  candidates;
- only high-confidence registry-only entries are described as probable orphans.
"""

import scanner_v040 as v040
from rules import finding

VERSION = "0.4.1"

SLEEP_OR_TRANSIENT_PLATFORMS = {"tesla_fleet", "mobile_app"}
SECONDARY_PLATFORMS = {"energy"}


def _platforms(item):
    values = item.get("platforms") or []
    if isinstance(values, str):
        return {values}
    return {str(x) for x in values if x}


def _calibrate_group(item, integration_name=None):
    result = dict(item)
    platforms = _platforms(result)
    if integration_name:
        platforms.add(str(integration_name))

    missing = int(result.get("missing_state", 0) or 0)
    unknown = int(result.get("unknown", 0) or 0)
    unavailable = int(result.get("unavailable", 0) or 0)

    if platforms & SECONDARY_PLATFORMS:
        result["status"] = "secondary"
        result["status_note"] = "Entités dérivées/secondaires : ne pas interpréter comme une intégration hors ligne."
        return result

    if platforms & SLEEP_OR_TRANSIENT_PLATFORMS and missing == 0:
        if "tesla_fleet" in platforms and unknown >= unavailable:
            result["status"] = "watch"
            result["status_note"] = "Valeurs Tesla potentiellement indisponibles pendant la veille du véhicule ; vérifier avant de conclure à une panne."
            result["transient_or_sleep_tolerant"] = True
        elif "mobile_app" in platforms and result.get("status") in {"offline", "degraded"}:
            result["status"] = "watch"
            result["status_note"] = "Les capteurs Companion App peuvent être indisponibles lorsque le terminal ne remonte pas de données."
            result["transient_or_sleep_tolerant"] = True

    return result


def _recount_registry(registry):
    integrations = ((registry.get("integration_health") or {}).get("groups") or [])
    devices = ((registry.get("device_health") or {}).get("groups") or [])

    calibrated_integrations = []
    for item in integrations:
        calibrated_integrations.append(_calibrate_group(item, item.get("integration")))

    calibrated_devices = []
    for item in devices:
        calibrated_devices.append(_calibrate_group(item))

    integration_health = dict(registry.get("integration_health") or {})
    integration_health["groups"] = calibrated_integrations
    integration_health["affected"] = sum(1 for x in calibrated_integrations if x.get("status") in {"offline", "degraded", "watch"})
    integration_health["problematic"] = sum(1 for x in calibrated_integrations if x.get("status") in {"offline", "degraded"})
    integration_health["offline"] = sum(1 for x in calibrated_integrations if x.get("status") == "offline")

    device_health = dict(registry.get("device_health") or {})
    device_health["groups"] = calibrated_devices
    device_health["affected"] = sum(1 for x in calibrated_devices if x.get("status") in {"offline", "degraded", "watch"})
    device_health["problematic"] = sum(1 for x in calibrated_devices if x.get("status") in {"offline", "degraded"})
    device_health["offline"] = sum(1 for x in calibrated_devices if x.get("status") == "offline")

    result = dict(registry)
    result["integration_health"] = integration_health
    result["device_health"] = device_health
    return result


def _calibrate_orphans(registry):
    result = dict(registry)
    orphan = dict(result.get("orphan_analysis") or {})
    candidates = list(orphan.get("candidates") or [])
    high = [x for x in candidates if x.get("confidence") == "high"]
    medium = [x for x in candidates if x.get("confidence") != "high"]

    orphan["probable_orphan_count"] = len(high)
    orphan["review_candidate_count"] = len(medium)
    orphan["probable_orphans"] = high[:50]
    orphan["local_unavailable_candidates"] = medium[:50]
    orphan["note"] = (
        "Seules les entrées actives présentes dans le registre mais sans aucun état sont qualifiées d'orphelins probables. "
        "Les entités locales simplement unavailable restent des candidats à vérifier, pas des orphelins."
    )
    result["orphan_analysis"] = orphan
    return result


def _remove_registry_findings(report):
    report["findings"] = [
        item for item in (report.get("findings") or [])
        if item.get("rule_id") not in {"HD-REG-001", "HD-REG-002"}
    ]


def _append_registry_findings(report, registry):
    orphan = registry.get("orphan_analysis") or {}
    probable = int(orphan.get("probable_orphan_count", 0) or 0)
    review = int(orphan.get("review_candidate_count", 0) or 0)

    if probable > 0:
        item = finding(
            "HD-REG-001",
            "Entités probablement orphelines dans le registre",
            "medium",
            "configuration",
            f"{probable} entrée(s) active(s) sont présentes dans le registre sans aucun état Home Assistant correspondant.",
            "Vérifier leur origine avant suppression. Ce signal est plus fiable qu'une simple entité unavailable, mais HA Doctor ne modifie jamais le registre.",
            examples=(orphan.get("probable_orphans") or [])[:12],
        )
        item["priority"] = "verify"
        item["priority_label"] = "À vérifier"
        report.setdefault("findings", []).append(item)

    if review > 0:
        item = finding(
            "HD-REG-002",
            "Entités locales indisponibles à revoir",
            "low",
            "configuration",
            f"{review} entité(s) locale(s) sans appareil associé sont actuellement unavailable, sans preuve suffisante qu'elles soient orphelines.",
            "Contrôler surtout les anciennes automatisations, scripts et helpers. Une configuration invalide ou temporairement non chargée peut produire le même symptôme.",
            examples=(orphan.get("local_unavailable_candidates") or [])[:12],
        )
        item["priority"] = "verify"
        item["priority_label"] = "À vérifier"
        report.setdefault("findings", []).append(item)


def scan(include_yaml=True):
    report = v040.scan(include_yaml=include_yaml)
    registry = report.get("registry_analysis") or {}

    if registry.get("available"):
        registry = _recount_registry(registry)
        registry = _calibrate_orphans(registry)
        report["registry_analysis"] = registry
        _remove_registry_findings(report)
        _append_registry_findings(report, registry)
        v040._resync_findings(report)

    report["version"] = VERSION
    score_meta = dict(report.get("score_meta") or {})
    score_meta.update({
        "model": "priority_v2.1-preview",
        "registry_scoring": False,
        "note": "0.4.1 calibre la veille/transience des intégrations et distingue les orphelins probables des entités locales simplement indisponibles. Le registre ne modifie toujours pas le score Alpha.",
    })
    report["score_meta"] = score_meta
    return report
