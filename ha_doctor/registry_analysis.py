"""Read-only Home Assistant registry analysis for HA Doctor 0.4.

Uses the official Supervisor WebSocket proxy and never reads .storage.
Only metadata needed for diagnostics is retained in the report; raw registry
payloads and authentication tokens are never persisted.
"""

from collections import defaultdict
import json
import os

try:
    import websocket
except ImportError:  # pragma: no cover - handled gracefully at runtime
    websocket = None

WS_URL = "ws://supervisor/core/websocket"

OPTIONAL_DOMAINS = {"button", "event", "image", "notify", "scene", "stt", "tts", "update"}
OPTIONAL_CATEGORIES = {"config", "diagnostic"}
LOCAL_CONFIG_DOMAINS = {
    "automation", "counter", "group", "input_boolean", "input_datetime",
    "input_number", "input_select", "input_text", "person", "scene",
    "script", "timer",
}
LOCAL_CONFIG_PLATFORMS = LOCAL_CONFIG_DOMAINS | {"template", "homeassistant"}


def _json_message(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return json.loads(raw)


def _command(ws, command_id, command_type):
    ws.send(json.dumps({"id": command_id, "type": command_type}))
    while True:
        message = _json_message(ws.recv())
        if message.get("id") != command_id:
            continue
        if not message.get("success"):
            error = message.get("error") or {}
            code = error.get("code") if isinstance(error, dict) else None
            raise RuntimeError(f"{command_type}:{code or 'command_failed'}")
        return message.get("result")


def _normalize_display_entities(payload):
    """Normalize config/entity_registry/list_for_display compact response."""
    if not isinstance(payload, dict):
        return []
    categories = payload.get("entity_categories") or {}
    entities = []
    for item in payload.get("entities") or []:
        if not isinstance(item, dict) or not item.get("ei"):
            continue
        category = item.get("ec")
        if category is not None:
            category = categories.get(str(category), categories.get(category))
        entities.append({
            "entity_id": item.get("ei"),
            "platform": item.get("pl"),
            "device_id": item.get("di"),
            "entity_category": category,
            "disabled_by": None,
            "config_entry_id": None,
        })
    return entities


def fetch_registries():
    """Fetch entity/device registries through the read-only HA WebSocket API.

    Returns a compact dict and never raises into the main scan. Full entity
    registry is preferred; the documented display endpoint is used as fallback.
    """
    errors = []
    token = os.getenv("SUPERVISOR_TOKEN")
    if websocket is None:
        return {"available": False, "entities": [], "devices": [], "errors": ["websocket_client_unavailable"]}
    if not token:
        return {"available": False, "entities": [], "devices": [], "errors": ["supervisor_token_unavailable"]}

    ws = None
    try:
        ws = websocket.create_connection(
            WS_URL,
            timeout=6,
            suppress_origin=True,
            http_no_proxy=["supervisor", "localhost", "127.0.0.1"],
        )
        hello = _json_message(ws.recv())
        if hello.get("type") == "auth_required":
            ws.send(json.dumps({"type": "auth", "access_token": token}))
            auth = _json_message(ws.recv())
        else:
            auth = hello
        if auth.get("type") != "auth_ok":
            return {"available": False, "entities": [], "devices": [], "errors": ["websocket_auth_failed"]}

        entities = []
        try:
            payload = _command(ws, 1, "config/entity_registry/list")
            if isinstance(payload, list):
                entities = [item for item in payload if isinstance(item, dict)]
        except Exception as exc:
            errors.append(type(exc).__name__ + ":entity_registry_full")
            try:
                payload = _command(ws, 2, "config/entity_registry/list_for_display")
                entities = _normalize_display_entities(payload)
            except Exception as fallback_exc:
                errors.append(type(fallback_exc).__name__ + ":entity_registry_display")

        devices = []
        try:
            payload = _command(ws, 3, "config/device_registry/list")
            if isinstance(payload, list):
                devices = [item for item in payload if isinstance(item, dict)]
        except Exception as exc:
            errors.append(type(exc).__name__ + ":device_registry")

        return {
            "available": bool(entities),
            "entities": entities,
            "devices": devices,
            "errors": errors,
        }
    except Exception as exc:
        return {
            "available": False,
            "entities": [],
            "devices": [],
            "errors": [type(exc).__name__ + ":websocket_connection"],
        }
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def _entity_category(entry):
    value = entry.get("entity_category")
    return str(value).lower() if value is not None else None


def _is_optional(entry):
    entity_id = str(entry.get("entity_id") or "")
    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    return domain in OPTIONAL_DOMAINS or _entity_category(entry) in OPTIONAL_CATEGORIES


def _state_status(entry, states_by_id):
    entity_id = str(entry.get("entity_id") or "")
    state = states_by_id.get(entity_id)
    if state is None:
        return "missing_state"
    current = state.get("state") if isinstance(state, dict) else None
    if current == "unavailable":
        return "unavailable"
    if current == "unknown":
        return "unknown"
    return "healthy"


def _bucket_status(core_total, core_affected):
    if core_total <= 0:
        return "secondary"
    ratio = core_affected / core_total
    if core_total >= 2 and ratio >= 0.80:
        return "offline"
    if core_affected >= 2 and ratio >= 0.25:
        return "degraded"
    if core_affected >= 1:
        return "watch"
    return "healthy"


def _new_bucket():
    return {
        "total": 0,
        "core_total": 0,
        "healthy": 0,
        "unavailable": 0,
        "unknown": 0,
        "missing_state": 0,
        "optional_affected": 0,
        "examples": [],
        "platforms": set(),
    }


def _add_entry(bucket, entry, status):
    bucket["total"] += 1
    optional = _is_optional(entry)
    if not optional:
        bucket["core_total"] += 1
    if status == "healthy":
        bucket["healthy"] += 1
    else:
        bucket[status] += 1
        if optional:
            bucket["optional_affected"] += 1
        elif len(bucket["examples"]) < 6:
            bucket["examples"].append(entry.get("entity_id"))
    platform = entry.get("platform")
    if platform:
        bucket["platforms"].add(str(platform))


def _finalize_bucket(bucket):
    core_affected = max(
        0,
        bucket["unavailable"] + bucket["unknown"] + bucket["missing_state"] - bucket["optional_affected"],
    )
    core_total = bucket["core_total"]
    result = {
        "total": bucket["total"],
        "core_total": core_total,
        "core_affected": core_affected,
        "healthy": bucket["healthy"],
        "unavailable": bucket["unavailable"],
        "unknown": bucket["unknown"],
        "missing_state": bucket["missing_state"],
        "optional_affected": bucket["optional_affected"],
        "affected_ratio": round(core_affected / core_total, 3) if core_total else 0.0,
        "status": _bucket_status(core_total, core_affected),
        "examples": [x for x in bucket["examples"] if x],
    }
    if bucket["platforms"]:
        result["platforms"] = sorted(bucket["platforms"])
    return result


def _device_name(device, representative=None):
    for key in ("name_by_user", "name", "model"):
        value = device.get(key) if isinstance(device, dict) else None
        if value:
            return str(value)
    return representative or "Appareil sans nom"


def _orphan_candidate(entry, status):
    entity_id = str(entry.get("entity_id") or "")
    if "." not in entity_id or _is_optional(entry):
        return None
    domain = entity_id.split(".", 1)[0]
    platform = str(entry.get("platform") or domain)
    if domain not in LOCAL_CONFIG_DOMAINS and platform not in LOCAL_CONFIG_PLATFORMS:
        return None
    if entry.get("device_id"):
        return None

    if status == "missing_state":
        confidence = "high"
        reason = "enabled_registry_entry_without_state"
    elif status == "unavailable":
        confidence = "medium"
        reason = "local_entity_unavailable_without_device"
    else:
        return None

    return {
        "entity_id": entity_id,
        "platform": platform,
        "confidence": confidence,
        "reason": reason,
    }


def analyze_registry(states, registry_payload):
    """Build compact integration/device health and probable orphan diagnostics."""
    entities = registry_payload.get("entities") or []
    devices = registry_payload.get("devices") or []
    states_by_id = {
        item.get("entity_id"): item
        for item in states or []
        if isinstance(item, dict) and isinstance(item.get("entity_id"), str)
    }
    device_map = {
        item.get("id"): item
        for item in devices
        if isinstance(item, dict) and item.get("id")
    }

    enabled = [
        item for item in entities
        if isinstance(item, dict)
        and item.get("entity_id")
        and item.get("disabled_by") in (None, "")
    ]

    integration_buckets = defaultdict(_new_bucket)
    device_buckets = defaultdict(_new_bucket)
    orphan_candidates = []
    registry_only = 0

    for entry in enabled:
        entity_id = str(entry.get("entity_id"))
        platform = str(entry.get("platform") or entity_id.split(".", 1)[0] or "unknown")
        status = _state_status(entry, states_by_id)
        _add_entry(integration_buckets[platform], entry, status)

        device_id = entry.get("device_id")
        if device_id:
            _add_entry(device_buckets[str(device_id)], entry, status)

        if status == "missing_state":
            registry_only += 1
        candidate = _orphan_candidate(entry, status)
        if candidate:
            orphan_candidates.append(candidate)

    integration_groups = []
    for platform, bucket in integration_buckets.items():
        item = {"integration": platform, **_finalize_bucket(bucket)}
        if item["status"] != "healthy" or item["optional_affected"]:
            integration_groups.append(item)
    status_rank = {"offline": 0, "degraded": 1, "watch": 2, "secondary": 3, "healthy": 4}
    integration_groups.sort(key=lambda x: (status_rank.get(x["status"], 9), -x["core_affected"], x["integration"]))

    device_groups = []
    for device_id, bucket in device_buckets.items():
        finalized = _finalize_bucket(bucket)
        if finalized["status"] == "healthy" and not finalized["optional_affected"]:
            continue
        meta = device_map.get(device_id) or {}
        representative = finalized["examples"][0] if finalized["examples"] else None
        item = {
            "name": _device_name(meta, representative),
            "manufacturer": meta.get("manufacturer"),
            "model": meta.get("model"),
            **finalized,
        }
        device_groups.append(item)
    device_groups.sort(key=lambda x: (status_rank.get(x["status"], 9), -x["core_affected"], x["name"]))

    orphan_candidates.sort(key=lambda x: (0 if x["confidence"] == "high" else 1, x["entity_id"]))
    high_confidence = sum(1 for item in orphan_candidates if item["confidence"] == "high")

    affected_integrations = sum(1 for item in integration_groups if item["status"] in {"offline", "degraded", "watch"})
    offline_integrations = sum(1 for item in integration_groups if item["status"] == "offline")
    affected_devices = sum(1 for item in device_groups if item["status"] in {"offline", "degraded", "watch"})

    return {
        "available": bool(registry_payload.get("available")),
        "entity_registry_count": len(enabled),
        "device_registry_count": len(device_map),
        "integration_health": {
            "total": len(integration_buckets),
            "affected": affected_integrations,
            "offline": offline_integrations,
            "groups": integration_groups[:30],
        },
        "device_health": {
            "total": len(device_map),
            "affected": affected_devices,
            "groups": device_groups[:30],
        },
        "orphan_analysis": {
            "registry_only_count": registry_only,
            "candidate_count": len(orphan_candidates),
            "high_confidence_count": high_confidence,
            "candidates": orphan_candidates[:50],
            "note": "Candidats uniquement : aucune suppression automatique. Une entité locale sans état ou indisponible peut aussi provenir d'une configuration temporairement invalide.",
        },
        "errors": list(registry_payload.get("errors") or []),
    }
