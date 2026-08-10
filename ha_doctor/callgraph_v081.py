"""HA Doctor 0.8.1 transitive script/scene call graph."""

from collections import Counter, deque
from pathlib import Path
import re
import unicodedata

import yaml

import scanner as core_scanner
import flow_v080 as flow

VERSION = "0.8.1"


def _domain(entity_id):
    value = str(entity_id or "")
    return value.split(".", 1)[0] if "." in value else ""


def _slugify(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return text


def _load_documents(report):
    root = Path(core_scanner.CONFIG_ROOT)
    wanted = {
        str(node.get("source"))
        for node in report.get("dependency_graph") or []
        if node.get("source")
    }
    for name in ("scripts.yaml", "scripts.yml", "scenes.yaml", "scenes.yml"):
        if (root / name).is_file():
            wanted.add(name)
    packages = root / "packages"
    if packages.exists():
        for path in packages.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}:
                try:
                    wanted.add(str(path.relative_to(root)))
                except Exception:
                    pass

    docs = {}
    errors = []
    total_bytes = 0
    for rel in sorted(wanted):
        path = root / rel
        if not path.is_file():
            continue
        try:
            if not core_scanner._should_read(path):
                continue
            size = path.stat().st_size
        except Exception:
            continue
        if size > core_scanner.MAX_FILE_BYTES:
            continue
        if total_bytes + size > core_scanner.MAX_TOTAL_BYTES:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            docs[rel] = yaml.load(text, Loader=core_scanner.HALoader)
            total_bytes += size
        except Exception as exc:
            errors.append({"file": rel, "error": type(exc).__name__})
    return docs, errors


def _analyze_definition(definition):
    if not isinstance(definition, dict):
        return {"calls": set(), "controls": set(), "services": set()}
    actions = definition.get(
        "sequence",
        definition.get("actions", definition.get("action", [])),
    )
    lineage = flow.resolve_variable_lineage(definition)
    visible_entities = flow._entity_ids(definition)
    calls = set()
    controls = set()
    services = set()

    for action in flow._walk_action_nodes(actions):
        action_name = str(action.get("action") or action.get("service") or "")
        if "." not in action_name:
            continue
        action_domain, action_verb = action_name.split(".", 1)
        services.add(action_name)

        if (
            action_domain in flow.CALL_DOMAINS
            and action_verb not in {"turn_on", "turn_off", "toggle", "reload", "trigger"}
            and flow.ENTITY_ID_RE.fullmatch(action_name)
        ):
            calls.add(action_name)

        for raw_target in flow._target_values(action):
            candidates, _confidence, _dynamic, _variables, _method = flow._resolve_target(
                raw_target, lineage, action_domain, visible_entities
            )
            if flow._is_read_only_action(action_name):
                continue
            for entity_id in candidates:
                if _domain(entity_id) in flow.CALL_DOMAINS or action_domain in flow.CALL_DOMAINS:
                    calls.add(entity_id)
                else:
                    controls.add(entity_id)
    return {"calls": calls, "controls": controls, "services": services}


def _definitions(report):
    docs, errors = _load_documents(report)
    scripts = {}
    scenes = {}

    def add_script(key, definition, source):
        entity_id = f"script.{_slugify(key)}"
        if entity_id == "script." or not isinstance(definition, dict):
            return
        analysis = _analyze_definition(definition)
        scripts[entity_id] = {
            "source": source,
            "calls": sorted(analysis["calls"]),
            "controls": sorted(analysis["controls"]),
            "service_endpoints": sorted(analysis["services"]),
        }

    for source, data in docs.items():
        if isinstance(data, dict):
            section = data.get("script")
            if isinstance(section, dict):
                for key, definition in section.items():
                    add_script(key, definition, source)
            if Path(source).name in {"scripts.yaml", "scripts.yml"}:
                for key, definition in data.items():
                    if isinstance(definition, dict):
                        add_script(key, definition, source)

        if Path(source).name in {"scenes.yaml", "scenes.yml"} and isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                entities = item.get("entities")
                if not name or not isinstance(entities, dict):
                    continue
                scenes[f"scene.{_slugify(name)}"] = {
                    "source": source,
                    "controls": sorted(
                        entity_id
                        for entity_id in entities
                        if isinstance(entity_id, str) and "." in entity_id
                    ),
                    "entity_id_confidence": 0.6,
                }
    return scripts, scenes, errors


def _script_cycles(scripts):
    cycles = []
    visited = set()
    active = []
    active_set = set()

    def visit(script_id):
        if script_id in active_set:
            try:
                index = active.index(script_id)
                cycle = active[index:] + [script_id]
            except ValueError:
                cycle = [script_id, script_id]
            if cycle not in cycles:
                cycles.append(cycle)
            return
        if script_id in visited or script_id not in scripts:
            return
        active.append(script_id)
        active_set.add(script_id)
        for target in scripts[script_id]["calls"]:
            if target.startswith("script."):
                visit(target)
        active.pop()
        active_set.discard(script_id)
        visited.add(script_id)

    for script_id in sorted(scripts):
        visit(script_id)
    return cycles


def build_transitive_call_graph(report):
    scripts, scenes, parse_errors = _definitions(report)
    cycles = _script_cycles(scripts)
    unresolved = set()
    transitive_edge_count = 0

    for node in report.get("dependency_graph") or []:
        queue = deque((target, 1) for target in node.get("calls") or [])
        seen = set()
        transitive_calls = []
        transitive_controls = set()
        service_endpoints = set()

        while queue:
            target, depth = queue.popleft()
            if target in seen or depth > 8:
                continue
            seen.add(target)
            if target in scripts:
                if depth > 1:
                    transitive_calls.append({"entity_id": target, "depth": depth})
                definition = scripts[target]
                transitive_controls.update(definition["controls"])
                service_endpoints.update(definition["service_endpoints"])
                for child in definition["calls"]:
                    queue.append((child, depth + 1))
                continue
            if target in scenes:
                if depth > 1:
                    transitive_calls.append({"entity_id": target, "depth": depth})
                transitive_controls.update(scenes[target]["controls"])
                continue
            if target.startswith(("script.", "scene.")):
                unresolved.add(target)

        node["transitive_calls"] = transitive_calls[:30]
        node["transitive_controls"] = sorted(transitive_controls)[:40]
        node["transitive_service_endpoints"] = sorted(service_endpoints)[:30]
        transitive_edge_count += len(transitive_calls) + len(transitive_controls)

    caller_counts = Counter()
    for node in report.get("dependency_graph") or []:
        for target in node.get("calls") or []:
            caller_counts[target] += 1
        for item in node.get("transitive_calls") or []:
            target = str(item.get("entity_id") or "")
            if target:
                caller_counts[target] += 1

    result = {
        "model": "transitive_call_graph_v1",
        "script_nodes": len(scripts),
        "scene_nodes_heuristic": len(scenes),
        "script_to_call_edges": sum(len(item["calls"]) for item in scripts.values()),
        "transitive_edge_count": transitive_edge_count,
        "recursion_cycle_count": len(cycles),
        "recursion_cycles": cycles[:12],
        "unresolved_call_target_count": len(unresolved),
        "unresolved_call_targets": sorted(unresolved)[:30],
        "call_hubs": [
            {"entity_id": entity_id, "automation_callers": count}
            for entity_id, count in caller_counts.most_common(20)
            if count >= 2
        ],
        "parse_errors": parse_errors[:12],
        "scene_id_resolution": "name_slug_heuristic_0.6",
        "raw_yaml_persisted": False,
        "call_payloads_persisted": False,
    }
    report["call_graph_analysis"] = result
    architecture = report.get("architecture_analysis") or {}
    architecture["transitive_call_graph_model"] = result["model"]
    architecture["script_definition_count"] = len(scripts)
    architecture["script_recursion_cycle_count"] = len(cycles)
    report.setdefault("privacy", {})["transitive_call_graph_raw_yaml_persisted"] = False
    return result
