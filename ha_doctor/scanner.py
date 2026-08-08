import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

from redaction import looks_sensitive_key
from rules import build_scores, evaluate

CONFIG_ROOT = Path(os.getenv("HA_DOCTOR_CONFIG", "/ha_config"))
SUPERVISOR_URL = os.getenv("SUPERVISOR_URL", "http://supervisor")
SUPERVISOR_TOKEN = os.getenv("SUPERVISOR_TOKEN", "")
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024

ENTITY_RE = re.compile(
    r"\b(?:alarm_control_panel|automation|binary_sensor|button|camera|climate|counter|cover|device_tracker|event|fan|humidifier|input_boolean|input_button|input_datetime|input_number|input_select|input_text|lawn_mower|light|lock|media_player|number|person|remote|scene|script|select|sensor|siren|switch|timer|update|vacuum|valve|water_heater|weather)\.[a-z0-9_]+\b",
    re.IGNORECASE,
)
SENSITIVE_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*:\s*(.+?)\s*$")
EXCLUDED_NAMES = {"secrets.yaml", "secrets.yml"}
EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".crt", ".p12", ".pfx", ".zip", ".tar", ".gz"}
EXCLUDED_PARTS = {"backups", "backup", "ssl"}


class HALoader(yaml.SafeLoader):
    pass


def _unknown_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


HALoader.add_multi_constructor("!", _unknown_tag)


def _api_get(path):
    url = f"{SUPERVISOR_URL}{path}"
    headers = {"Accept": "application/json"}
    if SUPERVISOR_TOKEN:
        headers["Authorization"] = f"Bearer {SUPERVISOR_TOKEN}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=8) as response:
        payload = response.read()
        return json.loads(payload.decode("utf-8")) if payload else None


def _safe_api_get(path, api_errors):
    try:
        return _api_get(path)
    except Exception as exc:  # scan must continue if a secondary info endpoint fails
        api_errors.append({"path": path, "error": type(exc).__name__})
        return None


def _unwrap_supervisor(payload):
    if isinstance(payload, dict) and "data" in payload and payload.get("result") in {"ok", None}:
        return payload.get("data")
    return payload


def _should_read(path: Path):
    rel_parts = {p.lower() for p in path.relative_to(CONFIG_ROOT).parts}
    name = path.name.lower()
    if name in EXCLUDED_NAMES:
        return False
    if path.suffix.lower() not in {".yaml", ".yml"}:
        return False
    if any(part in EXCLUDED_PARTS for part in rel_parts):
        return False
    if ".storage" in rel_parts:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return True


def _extract_entities(obj):
    found = set()
    if isinstance(obj, str):
        found.update(m.group(0).lower() for m in ENTITY_RE.finditer(obj))
    elif isinstance(obj, list):
        for item in obj:
            found.update(_extract_entities(item))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            found.update(_extract_entities(key))
            found.update(_extract_entities(value))
    return found


def _extract_target_entities(obj):
    """Extract explicit entity_id targets from an action subtree."""
    found = set()
    if isinstance(obj, list):
        for item in obj:
            found.update(_extract_target_entities(item))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if str(key) == "entity_id":
                found.update(_extract_entities(value))
            else:
                found.update(_extract_target_entities(value))
    return found


def _delay_seconds(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # HH:MM:SS, ignore templated delays
        if "{{" in value or "{%" in value:
            return 0
        parts = value.strip().split(":")
        try:
            if len(parts) == 3:
                h, m, s = [float(x) for x in parts]
                return h * 3600 + m * 60 + s
            return float(value)
        except ValueError:
            return 0
    if isinstance(value, dict):
        try:
            return (
                float(value.get("days", 0)) * 86400
                + float(value.get("hours", 0)) * 3600
                + float(value.get("minutes", 0)) * 60
                + float(value.get("seconds", 0))
                + float(value.get("milliseconds", 0)) / 1000
            )
        except (TypeError, ValueError):
            return 0
    return 0


def _max_delay(obj):
    current = 0
    if isinstance(obj, list):
        for item in obj:
            current = max(current, _max_delay(item))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if str(key) == "delay":
                current = max(current, _delay_seconds(value))
            current = max(current, _max_delay(value))
    return current


def _normalize_automation(item, source):
    if not isinstance(item, dict):
        return None
    if not any(k in item for k in ("trigger", "triggers")) or not any(k in item for k in ("action", "actions")):
        return None
    actions = item.get("actions", item.get("action", []))
    return {
        "id": str(item.get("id", "")) if item.get("id") is not None else None,
        "alias": item.get("alias") or item.get("name") or "Automation sans nom",
        "mode": item.get("mode", "single"),
        "enabled": item.get("enabled", True) if isinstance(item.get("enabled", True), bool) else True,
        "source": source,
        "referenced_entities": sorted(_extract_entities(item)),
        "controlled_entities": sorted(_extract_target_entities(actions)),
        "max_delay_seconds": round(_max_delay(actions), 3),
    }


def _collect_automations(data, source):
    autos = []
    if isinstance(data, list):
        # automations.yaml commonly is a root list
        for item in data:
            auto = _normalize_automation(item, source)
            if auto:
                autos.append(auto)
    elif isinstance(data, dict):
        # A package can contain automation: [ ... ] or automation: {name: {...}}
        for key, value in data.items():
            if str(key) == "automation":
                if isinstance(value, list):
                    for item in value:
                        auto = _normalize_automation(item, source)
                        if auto:
                            autos.append(auto)
                elif isinstance(value, dict):
                    for name, item in value.items():
                        if isinstance(item, dict) and "alias" not in item:
                            item = dict(item)
                            item["alias"] = str(name)
                        auto = _normalize_automation(item, source)
                        if auto:
                            autos.append(auto)
            elif isinstance(value, (dict, list)) and str(key) not in {"blueprint"}:
                # Do not recursively treat blueprint definitions as active automations.
                if "blueprints" not in source.replace("\\", "/"):
                    autos.extend(_collect_automations(value, source))
    return autos


def _scan_yaml(live_entity_ids):
    result = {
        "files_scanned": 0,
        "bytes_scanned": 0,
        "entity_references": [],
        "missing_entity_references": [],
        "potential_inline_secrets": [],
        "automations": [],
        "parse_errors": [],
        "skipped_files": [],
    }
    all_refs = set()
    ref_locations = defaultdict(list)
    total_bytes = 0

    if not CONFIG_ROOT.exists():
        result["parse_errors"].append({"file": str(CONFIG_ROOT), "error": "configuration directory not mounted"})
        return result

    for path in sorted(CONFIG_ROOT.rglob("*")):
        if not path.is_file() or not _should_read(path):
            continue
        rel = str(path.relative_to(CONFIG_ROOT))
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES or total_bytes + size > MAX_TOTAL_BYTES:
            result["skipped_files"].append({"file": rel, "reason": "size_limit", "bytes": size})
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            result["skipped_files"].append({"file": rel, "reason": type(exc).__name__})
            continue

        total_bytes += size
        result["files_scanned"] += 1
        result["bytes_scanned"] = total_bytes

        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in ENTITY_RE.finditer(line):
                entity_id = match.group(0).lower()
                all_refs.add(entity_id)
                if len(ref_locations[entity_id]) < 5:
                    ref_locations[entity_id].append({"file": rel, "line": lineno})

            sensitive = SENSITIVE_LINE_RE.match(line)
            if sensitive and looks_sensitive_key(sensitive.group(1)):
                raw_value = sensitive.group(2).strip()
                # !secret is the desired pattern and must never be flagged.
                if raw_value and not raw_value.startswith("!secret") and raw_value not in {"null", "None", "~", "{}", "[]"}:
                    result["potential_inline_secrets"].append({
                        "file": rel,
                        "line": lineno,
                        "key": sensitive.group(1),
                    })

        try:
            data = yaml.load(text, Loader=HALoader)
            result["automations"].extend(_collect_automations(data, rel))
        except Exception as exc:
            result["parse_errors"].append({"file": rel, "error": type(exc).__name__})

    result["entity_references"] = sorted(all_refs)
    for entity_id in sorted(all_refs - set(live_entity_ids)):
        # References to an automation/script/scene can legitimately be loaded later;
        # still useful, but keep the evidence compact and let the rule label it heuristic.
        result["missing_entity_references"].append({
            "entity_id": entity_id,
            "locations": ref_locations[entity_id],
        })

    # Deduplicate automations by (id, alias, source)
    seen = set()
    deduped = []
    for auto in result["automations"]:
        key = (auto.get("id"), auto.get("alias"), auto.get("source"))
        if key not in seen:
            seen.add(key)
            deduped.append(auto)
    result["automations"] = deduped
    return result


def _severity_counts(findings):
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for item in findings:
        sev = item.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def scan(include_yaml=True):
    started = time.time()
    api_errors = []

    config = _safe_api_get("/core/api/config", api_errors) or {}
    states = _safe_api_get("/core/api/states", api_errors) or []
    supervisor = _unwrap_supervisor(_safe_api_get("/supervisor/info", api_errors) or {}) or {}
    core_info = _unwrap_supervisor(_safe_api_get("/core/info", api_errors) or {}) or {}
    host_info = _unwrap_supervisor(_safe_api_get("/host/info", api_errors) or {}) or {}

    if not isinstance(states, list):
        states = []
    live_ids = {s.get("entity_id") for s in states if isinstance(s, dict) and s.get("entity_id")}

    yaml_result = _scan_yaml(live_ids) if include_yaml else {
        "files_scanned": 0,
        "bytes_scanned": 0,
        "entity_references": [],
        "missing_entity_references": [],
        "potential_inline_secrets": [],
        "automations": [],
        "parse_errors": [],
        "skipped_files": [],
    }

    snapshot = {
        "config": {
            "version": config.get("version"),
            "location_name": config.get("location_name"),
            "time_zone": config.get("time_zone"),
            "unit_system": config.get("unit_system"),
            "components_count": len(config.get("components", [])) if isinstance(config.get("components"), list) else None,
        },
        "states": states,
        "supervisor": {
            "version": supervisor.get("version"),
            "healthy": supervisor.get("healthy"),
            "supported": supervisor.get("supported"),
        },
        "core": {
            "version": core_info.get("version"),
            "machine": core_info.get("machine"),
            "image": core_info.get("image"),
        },
        "host": {
            "operating_system": host_info.get("operating_system"),
            "kernel": host_info.get("kernel"),
            "hostname": host_info.get("hostname"),
        },
        "yaml": yaml_result,
        "api_errors": api_errors,
    }

    findings = evaluate(snapshot)
    scores = build_scores(findings)

    # Do not persist raw states in the report: only aggregate, non-sensitive inventory.
    domain_counts = defaultdict(int)
    unavailable = []
    unknown = []
    for state in states:
        entity_id = state.get("entity_id", "") if isinstance(state, dict) else ""
        if "." in entity_id:
            domain_counts[entity_id.split(".", 1)[0]] += 1
        if isinstance(state, dict) and state.get("state") == "unavailable":
            unavailable.append(entity_id)
        if isinstance(state, dict) and state.get("state") == "unknown":
            unknown.append(entity_id)

    report = {
        "product": "HA Doctor",
        "version": "0.1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scan_duration_seconds": round(time.time() - started, 3),
        "privacy": {
            "mode": "local_read_only",
            "secrets_yaml_read": False,
            "raw_states_persisted": False,
            "configuration_mount": "read_only",
        },
        "home_assistant": snapshot["config"],
        "supervisor": snapshot["supervisor"],
        "core": snapshot["core"],
        "host": snapshot["host"],
        "inventory": {
            "states": len(states),
            "domains": dict(sorted(domain_counts.items())),
            "unavailable_count": len(unavailable),
            "unknown_count": len(unknown),
            "unavailable_examples": unavailable[:20],
            "unknown_examples": unknown[:20],
            "yaml_files_scanned": yaml_result.get("files_scanned", 0),
            "yaml_bytes_scanned": yaml_result.get("bytes_scanned", 0),
            "automations_detected": len(yaml_result.get("automations", [])),
            "entity_references_detected": len(yaml_result.get("entity_references", [])),
        },
        "scores": scores,
        "severity_counts": _severity_counts(findings),
        "findings": findings,
        "dependency_graph": [
            {
                "automation": a.get("alias"),
                "source": a.get("source"),
                "controls": a.get("controlled_entities", []),
                "references": a.get("referenced_entities", []),
            }
            for a in yaml_result.get("automations", [])
        ],
        "diagnostics": {
            "api_errors": api_errors,
            "yaml_parse_errors": yaml_result.get("parse_errors", []),
            "skipped_files": yaml_result.get("skipped_files", []),
        },
    }
    return report
