"""HA Doctor 0.8.1 conservative operational-context calibration."""
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION = "0.8.1"
SOLAR_MARKERS = ("solar", "photovolta", "inverter", "onduleur")
HEATING_MARKERS = ("radiateur", "heater", "heating", "thermostat", "malao", "kenya")


def _state_index(states):
    return {x.get("entity_id"): x.get("state") for x in (states or []) if isinstance(x, dict) and isinstance(x.get("entity_id"), str)}


def _local_dt(report):
    raw = str(report.get("generated_at") or "")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        value = datetime.now().astimezone()
    name = str((report.get("home_assistant") or {}).get("time_zone") or "")
    if name:
        try:
            value = value.astimezone(ZoneInfo(name))
        except Exception:
            pass
    return value, name


def _recount(registry):
    for key in ("integration_health", "device_health"):
        section = registry.get(key) or {}
        groups = section.get("groups") or []
        section["affected"] = sum(1 for x in groups if x.get("status") in {"offline", "degraded", "watch"})
        section["problematic"] = sum(1 for x in groups if x.get("status") in {"offline", "degraded"})
        section["offline"] = sum(1 for x in groups if x.get("status") == "offline")


def _drop_from_plan(report, ids):
    ids = set(ids)
    for key in ("action_plan", "recommendation_queue"):
        section = report.get(key) or {}
        section["items"] = [x for x in section.get("items") or [] if x.get("id") not in ids]
        if "top" in section:
            section["top"] = [x for x in section.get("top") or [] if x.get("id") not in ids]


def calibrate_operational_context(report, states):
    sun_state = _state_index(states).get("sun.sun")
    local_dt, tz_name = _local_dt(report)
    summer = tz_name.startswith("Europe/") and local_dt.month in {5, 6, 7, 8, 9}
    registry = report.get("registry_analysis") or {}
    solar, seasonal = set(), set()

    integrations = ((registry.get("integration_health") or {}).get("groups") or [])
    for group in integrations:
        name = str(group.get("integration") or "")
        if (
            group.get("status") == "offline"
            and sun_state == "below_horizon"
            and any(marker in name.lower() for marker in SOLAR_MARKERS)
            and int(group.get("missing_state", 0) or 0) == 0
        ):
            group.update({
                "status": "watch",
                "contextual_status": "solar_night_window",
                "context_factor": 0.30,
                "status_note": "Intégration solaire observée lorsque sun.sun est below_horizon ; confirmer après le lever avant de conclure à une panne.",
            })
            solar.add(name)

    devices = ((registry.get("device_health") or {}).get("groups") or [])
    for group in devices:
        platforms = {str(x) for x in group.get("platforms") or []}
        text = " ".join(str(group.get(k) or "") for k in ("name", "manufacturer", "model")).lower()
        solar_platform = any(any(m in p.lower() for m in SOLAR_MARKERS) for p in platforms)
        if group.get("status") == "offline" and sun_state == "below_horizon" and solar_platform:
            group.update({"status": "watch", "contextual_status": "solar_night_window", "context_factor": 0.30})
        elif group.get("status") == "offline" and summer and any(marker in text for marker in HEATING_MARKERS):
            group.update({
                "status": "watch",
                "contextual_status": "seasonal_heating_inactive_possible",
                "context_factor": 0.55,
                "status_note": "Équipement de chauffage hors ligne pendant la saison chaude ; vérifier s'il est volontairement coupé.",
            })
            seasonal.add(str(group.get("name") or ""))

    _recount(registry)
    suppressed = {f"DX-REG-INT-{name}" for name in solar}
    if seasonal:
        suppressed.add("DX-REG-CLUSTER-overkiz")
    for item in report.get("diagnostic_explanations") or []:
        if item.get("id") in suppressed:
            item["priority"] = "info"
            item["priority_label"] = "Informations"
            item["context_deescalated"] = True
            item["why_now"] = "Contexte opérationnel compatible avec une indisponibilité attendue ; confirmer dans une fenêtre pertinente."
    _drop_from_plan(report, suppressed)

    result = {
        "model": "operational_context_v1",
        "local_month": local_dt.month,
        "time_zone": tz_name,
        "sun_state": sun_state,
        "solar_integrations_deescalated": sorted(solar),
        "seasonal_heating_devices_deescalated": sorted(seasonal),
        "diagnostics_deescalated": sorted(suppressed),
        "health_score_recomputed": False,
    }
    report["operational_context"] = result
    return result
