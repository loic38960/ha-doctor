import copy
import ipaddress
import json
import os
import re
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

from redaction import looks_sensitive_key
from rules import build_scores, evaluate

VERSION = "0.2.0"
CONFIG_ROOT = Path(os.getenv("HA_DOCTOR_CONFIG", "/ha_config"))
SUPERVISOR_URL = os.getenv("SUPERVISOR_URL", "http://supervisor")
SUPERVISOR_TOKEN = os.getenv("SUPERVISOR_TOKEN", "")
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024

ENTITY_RE = re.compile(
    r"\b(?:alarm_control_panel|automation|binary_sensor|button|camera|climate|counter|cover|device_tracker|event|fan|humidifier|input_boolean|input_button|input_datetime|input_number|input_select|input_text|lawn_mower|light|lock|media_player|number|person|remote|scene|script|select|sensor|siren|switch|timer|todo|update|vacuum|valve|water_heater|weather)\.[a-z0-9_]+\b",
    re.IGNORECASE,
)
SENSITIVE_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*:\s*(.+?)\s*$")
EXCLUDED_NAMES = {"secrets.yaml", "secrets.yml"}
EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".crt", ".p12", ".pfx", ".zip", ".tar", ".gz"}
EXCLUDED_PARTS = {"backups", "backup", "ssl"}
ACTION_SEQUENCE_KEYS = {"sequence", "default", "then", "else", "parallel"}


class InputRef(str):
    """Represents a Home Assistant !input reference inside a blueprint."""


class HALoader(yaml.SafeLoader):
    pass


def _input_tag(loader, node):
    return InputRef(loader.construct_scalar(node))


def _unknown_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


HALoader.add_constructor("!input", _input_tag)
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
    except Exception as exc:
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


def _action_name(action):
    if not isinstance(action, dict):
        return None
    name = action.get("action") or action.get("service")
    return str(name) if isinstance(name, str) else None


def _is_read_only_action(action_name):
    if not action_name or "." not in action_name:
        return False
    verb = action_name.split(".", 1)[1].lower()
    return verb.startswith(("get_", "list_", "query_")) or verb in {"get", "list"}


def _target_entities_from_action(action):
    if not isinstance(action, dict):
        return set()
    name = _action_name(action)
    if not name or _is_read_only_action(name):
        return set()
    found = set()
    target = action.get("target")
    if isinstance(target, dict) and "entity_id" in target:
        found.update(_extract_entities(target.get("entity_id")))
    data = action.get("data")
    if isinstance(data, dict) and "entity_id" in data:
        found.update(_extract_entities(data.get("entity_id")))
    return found


def _walk_action_nodes(obj):
    """Yield action dictionaries without treating conditions as control actions."""
    if isinstance(obj, list):
        for item in obj:
            yield from _walk_action_nodes(item)
        return
    if not isinstance(obj, dict):
        return

    if _action_name(obj):
        yield obj

    choose = obj.get("choose")
    if isinstance(choose, list):
        for branch in choose:
            if isinstance(branch, dict):
                yield from _walk_action_nodes(branch.get("sequence", []))

    repeat = obj.get("repeat")
    if isinstance(repeat, dict):
        yield from _walk_action_nodes(repeat.get("sequence", []))

    for key in ACTION_SEQUENCE_KEYS:
        if key in obj:
            yield from _walk_action_nodes(obj.get(key))


def _extract_target_entities(actions):
    found = set()
    for action in _walk_action_nodes(actions):
        found.update(_target_entities_from_action(action))
    return found


def _extract_action_names(actions):
    return sorted({name for node in _walk_action_nodes(actions) if (name := _action_name(node))})


def _delay_seconds(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
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


def _max_wait_timeout(obj):
    current = 0
    if isinstance(obj, list):
        for item in obj:
            current = max(current, _max_wait_timeout(item))
    elif isinstance(obj, dict):
        if ("wait_template" in obj or "wait_for_trigger" in obj) and "timeout" in obj:
            current = max(current, _delay_seconds(obj.get("timeout")))
        for value in obj.values():
            current = max(current, _max_wait_timeout(value))
    return current


def _canonical_action(action):
    if not isinstance(action, dict):
        return None
    normalized = {k: v for k, v in action.items() if k not in {"alias", "enabled"}}
    try:
        return json.dumps(normalized, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(normalized)


def _find_consecutive_duplicate_actions(obj, path="action"):
    duplicates = []
    if isinstance(obj, list):
        previous_sig = None
        previous_idx = None
        for idx, item in enumerate(obj):
            sig = _canonical_action(item)
            if sig is not None and sig == previous_sig:
                duplicates.append({
                    "path": f"{path}[{previous_idx}]/{path}[{idx}]",
                    "action": _action_name(item) or next(iter(item), "action identique") if isinstance(item, dict) else "action identique",
                })
            previous_sig = sig
            previous_idx = idx
            duplicates.extend(_find_consecutive_duplicate_actions(item, f"{path}[{idx}]"))
    elif isinstance(obj, dict):
        choose = obj.get("choose")
        if isinstance(choose, list):
            for idx, branch in enumerate(choose):
                if isinstance(branch, dict):
                    duplicates.extend(_find_consecutive_duplicate_actions(branch.get("sequence", []), f"{path}.choose[{idx}].sequence"))
        repeat = obj.get("repeat")
        if isinstance(repeat, dict):
            duplicates.extend(_find_consecutive_duplicate_actions(repeat.get("sequence", []), f"{path}.repeat.sequence"))
        for key in ACTION_SEQUENCE_KEYS:
            if key in obj:
                duplicates.extend(_find_consecutive_duplicate_actions(obj.get(key), f"{path}.{key}"))
    return duplicates


def _extract_state_guards(conditions):
    guards = defaultdict(set)

    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            kind = obj.get("condition")
            if kind == "state":
                entities = _extract_entities(obj.get("entity_id"))
                states = obj.get("state")
                if not isinstance(states, list):
                    states = [states] if states is not None else []
                for entity in entities:
                    for state in states:
                        if isinstance(state, (str, int, float, bool)):
                            guards[entity].add(str(state))
            for key in ("conditions",):
                if key in obj:
                    walk(obj.get(key))

    walk(conditions)
    return {k: sorted(v) for k, v in guards.items()}


def _time_pattern_min_interval(triggers):
    minimum = None

    def parse_step(value, unit_seconds):
        if isinstance(value, int):
            return unit_seconds
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("/"):
                try:
                    return max(1, int(value[1:])) * unit_seconds
                except ValueError:
                    return None
        return None

    nodes = triggers if isinstance(triggers, list) else [triggers]
    for trigger in nodes:
        if not isinstance(trigger, dict):
            continue
        kind = trigger.get("trigger", trigger.get("platform"))
        if kind != "time_pattern":
            continue
        candidates = [
            parse_step(trigger.get("seconds"), 1),
            parse_step(trigger.get("minutes"), 60),
            parse_step(trigger.get("hours"), 3600),
        ]
        candidates = [x for x in candidates if x]
        if candidates:
            candidate = min(candidates)
            minimum = candidate if minimum is None else min(minimum, candidate)
    return minimum


def _resolve_inputs(obj, inputs):
    if isinstance(obj, InputRef):
        key = str(obj)
        return copy.deepcopy(inputs.get(key, key))
    if isinstance(obj, list):
        return [_resolve_inputs(item, inputs) for item in obj]
    if isinstance(obj, dict):
        return {_resolve_inputs(key, inputs): _resolve_inputs(value, inputs) for key, value in obj.items()}
    return obj


def _blueprint_key(source):
    normalized = source.replace("\\", "/")
    marker = "blueprints/automation/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return None


def _build_blueprint_registry(parsed_docs):
    registry = {}
    for source, data in parsed_docs.items():
        key = _blueprint_key(source)
        if not key or not isinstance(data, dict):
            continue
        meta = data.get("blueprint")
        if not isinstance(meta, dict) or meta.get("domain") != "automation":
            continue
        registry[key] = {"source": source, "data": data}
    return registry


def _find_blueprint(path, registry):
    if not isinstance(path, str):
        return None
    normalized = path.replace("\\", "/").lstrip("/")
    if normalized in registry:
        return registry[normalized]
    matches = [bp for key, bp in registry.items() if key.endswith(normalized) or normalized.endswith(key)]
    return matches[0] if len(matches) == 1 else None


def _expand_blueprint(item, registry):
    use = item.get("use_blueprint") if isinstance(item, dict) else None
    if not isinstance(use, dict):
        return None, None
    path = use.get("path")
    blueprint = _find_blueprint(path, registry)
    if not blueprint:
        return None, {"path": path, "reason": "not_found"}

    data = blueprint["data"]
    meta = data.get("blueprint", {})
    definitions = meta.get("input", {}) if isinstance(meta, dict) else {}
    inputs = {}
    if isinstance(definitions, dict):
        for name, definition in definitions.items():
            if isinstance(definition, dict) and "default" in definition:
                inputs[name] = copy.deepcopy(definition.get("default"))
    supplied = use.get("input", {})
    if isinstance(supplied, dict):
        inputs.update(copy.deepcopy(supplied))

    expanded = dict(item)
    for key in ("trigger", "triggers", "condition", "conditions", "action", "actions", "variables"):
        if key in data:
            expanded[key] = _resolve_inputs(copy.deepcopy(data[key]), inputs)
    if "mode" not in expanded and "mode" in data:
        expanded["mode"] = data.get("mode")
    expanded["__blueprint_path"] = str(path)
    expanded["__blueprint_source"] = blueprint["source"]
    return expanded, None


def _normalize_automation(item, source, blueprint_registry):
    if not isinstance(item, dict):
        return None

    blueprint_path = None
    blueprint_resolved = None
    blueprint_error = None
    effective = item
    if "use_blueprint" in item:
        blueprint_path = item.get("use_blueprint", {}).get("path") if isinstance(item.get("use_blueprint"), dict) else None
        effective, blueprint_error = _expand_blueprint(item, blueprint_registry)
        blueprint_resolved = effective is not None
        if effective is None:
            effective = item

    has_trigger = any(k in effective for k in ("trigger", "triggers"))
    has_action = any(k in effective for k in ("action", "actions"))
    if not (has_trigger and has_action) and "use_blueprint" not in item:
        return None

    actions = effective.get("actions", effective.get("action", []))
    triggers = effective.get("triggers", effective.get("trigger", []))
    conditions = effective.get("conditions", effective.get("condition", []))
    referenced = _extract_entities(effective)
    referenced.update(_extract_entities(item.get("use_blueprint", {})))

    return {
        "id": str(item.get("id", "")) if item.get("id") is not None else None,
        "alias": item.get("alias") or item.get("name") or "Automation sans nom",
        "mode": effective.get("mode", item.get("mode", "single")),
        "enabled": item.get("enabled", True) if isinstance(item.get("enabled", True), bool) else True,
        "source": source,
        "blueprint_path": blueprint_path,
        "blueprint_resolved": blueprint_resolved,
        "blueprint_error": blueprint_error,
        "referenced_entities": sorted(referenced),
        "trigger_entities": sorted(_extract_entities(triggers)),
        "controlled_entities": sorted(_extract_target_entities(actions)),
        "action_names": _extract_action_names(actions),
        "state_guards": _extract_state_guards(conditions),
        "max_delay_seconds": round(_max_delay(actions), 3),
        "max_wait_timeout_seconds": round(_max_wait_timeout(actions), 3),
        "min_time_pattern_interval_seconds": _time_pattern_min_interval(triggers),
        "consecutive_duplicate_actions": _find_consecutive_duplicate_actions(actions),
    }


def _collect_automations(data, source, blueprint_registry):
    autos = []
    if isinstance(data, list):
        for item in data:
            auto = _normalize_automation(item, source, blueprint_registry)
            if auto:
                autos.append(auto)
    elif isinstance(data, dict):
        for key, value in data.items():
            if str(key) == "automation":
                if isinstance(value, list):
                    for item in value:
                        auto = _normalize_automation(item, source, blueprint_registry)
                        if auto:
                            autos.append(auto)
                elif isinstance(value, dict):
                    for name, item in value.items():
                        if isinstance(item, dict) and "alias" not in item:
                            item = dict(item)
                            item["alias"] = str(name)
                        auto = _normalize_automation(item, source, blueprint_registry)
                        if auto:
                            autos.append(auto)
            elif isinstance(value, (dict, list)) and str(key) not in {"blueprint"}:
                if "blueprints" not in source.replace("\\", "/"):
                    autos.extend(_collect_automations(value, source, blueprint_registry))
    return autos


def _configuration_summary(data):
    summary = {
        "recorder_purge_keep_days": None,
        "http_use_x_forwarded_for": None,
        "trusted_proxies_count": 0,
        "trusted_proxy_all_network": False,
    }
    if not isinstance(data, dict):
        return summary

    recorder = data.get("recorder")
    if isinstance(recorder, dict):
        summary["recorder_purge_keep_days"] = recorder.get("purge_keep_days")

    http = data.get("http")
    if isinstance(http, dict):
        summary["http_use_x_forwarded_for"] = http.get("use_x_forwarded_for")
        proxies = http.get("trusted_proxies", [])
        if not isinstance(proxies, list):
            proxies = [proxies]
        summary["trusted_proxies_count"] = len(proxies)
        for proxy in proxies:
            if not isinstance(proxy, str):
                continue
            try:
                network = ipaddress.ip_network(proxy, strict=False)
                if network.prefixlen == 0:
                    summary["trusted_proxy_all_network"] = True
            except ValueError:
                if proxy.strip() in {"0.0.0.0", "::"}:
                    summary["trusted_proxy_all_network"] = True
    return summary


def _scan_yaml(live_entity_ids):
    result = {
        "files_scanned": 0,
        "bytes_scanned": 0,
        "entity_references": [],
        "missing_entity_references": [],
        "potential_inline_secrets": [],
        "automations": [],
        "blueprints_detected": 0,
        "unresolved_blueprints": [],
        "configuration": {},
        "parse_errors": [],
        "skipped_files": [],
    }
    all_refs = set()
    ref_locations = defaultdict(list)
    total_bytes = 0
    parsed_docs = {}

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

        is_blueprint_definition = _blueprint_key(rel) is not None
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not is_blueprint_definition:
                for match in ENTITY_RE.finditer(line):
                    entity_id = match.group(0).lower()
                    all_refs.add(entity_id)
                    if len(ref_locations[entity_id]) < 5:
                        ref_locations[entity_id].append({"file": rel, "line": lineno})

            sensitive = SENSITIVE_LINE_RE.match(line)
            if sensitive and looks_sensitive_key(sensitive.group(1)):
                raw_value = sensitive.group(2).strip()
                if raw_value and not raw_value.startswith("!secret") and raw_value not in {"null", "None", "~", "{}", "[]"}:
                    result["potential_inline_secrets"].append({
                        "file": rel,
                        "line": lineno,
                        "key": sensitive.group(1),
                    })

        try:
            parsed_docs[rel] = yaml.load(text, Loader=HALoader)
        except Exception as exc:
            result["parse_errors"].append({"file": rel, "error": type(exc).__name__})

    blueprint_registry = _build_blueprint_registry(parsed_docs)
    result["blueprints_detected"] = len(blueprint_registry)

    for source, data in parsed_docs.items():
        if source.replace("\\", "/").endswith("configuration.yaml"):
            result["configuration"] = _configuration_summary(data)
        result["automations"].extend(_collect_automations(data, source, blueprint_registry))

    for auto in result["automations"]:
        for entity_id in auto.get("referenced_entities", []):
            all_refs.add(entity_id)
            if not ref_locations[entity_id]:
                ref_locations[entity_id].append({"file": auto.get("source"), "line": None})

    result["entity_references"] = sorted(all_refs)
    for entity_id in sorted(all_refs - set(live_entity_ids)):
        result["missing_entity_references"].append({
            "entity_id": entity_id,
            "locations": ref_locations[entity_id],
        })

    seen = set()
    deduped = []
    for auto in result["automations"]:
        key = (auto.get("id"), auto.get("alias"), auto.get("source"))
        if key not in seen:
            seen.add(key)
            deduped.append(auto)
        if auto.get("blueprint_resolved") is False:
            result["unresolved_blueprints"].append({
                "alias": auto.get("alias"),
                "source": auto.get("source"),
                "path": auto.get("blueprint_path"),
            })
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
        "blueprints_detected": 0,
        "unresolved_blueprints": [],
        "configuration": {},
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
        "version": VERSION,
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
            "blueprints_detected": yaml_result.get("blueprints_detected", 0),
            "entity_references_detected": len(yaml_result.get("entity_references", [])),
        },
        "scores": scores,
        "severity_counts": _severity_counts(findings),
        "findings": findings,
        "dependency_graph": [
            {
                "automation": a.get("alias"),
                "source": a.get("source"),
                "blueprint": a.get("blueprint_path"),
                "controls": a.get("controlled_entities", []),
                "triggers_on": a.get("trigger_entities", []),
                "references": a.get("referenced_entities", []),
            }
            for a in yaml_result.get("automations", [])
        ],
        "diagnostics": {
            "api_errors": api_errors,
            "yaml_parse_errors": yaml_result.get("parse_errors", []),
            "skipped_files": yaml_result.get("skipped_files", []),
            "unresolved_blueprints": yaml_result.get("unresolved_blueprints", []),
        },
    }
    return report
