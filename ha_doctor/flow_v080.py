"""HA Doctor 0.8 semantic entity-flow engine.

Read-only local analysis. The engine reparses only automation sources and blueprint
definitions already covered by HA Doctor, resolves simple variable lineage and
classifies action edges as controls, calls, or unresolved dynamic targets.

No raw YAML, template text, state values, secrets, or registry payloads are
persisted in the generated report.
"""

from collections import defaultdict
from pathlib import Path
import re

import yaml

import scanner as core_scanner
import intelligence_v070 as v070

VERSION = "0.8.0"
MODEL = "entity_flow_v3"

CALL_DOMAINS = {"script", "scene", "automation"}
JINJA_MARKERS = ("{{", "{%")
IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
ENTITY_ID_RE = re.compile(
    r"\b(?:alarm_control_panel|automation|binary_sensor|button|calendar|camera|climate|counter|cover|datetime|device_tracker|event|fan|group|image|input_boolean|input_datetime|input_number|input_select|input_text|lawn_mower|light|lock|media_player|notify|number|person|remote|scene|script|select|sensor|siren|stt|sun|switch|text|time|timer|todo|tts|update|vacuum|valve|water_heater|weather|zone)\.[A-Za-z0-9_]+\b"
)

READ_ONLY_VERBS = {
    "get", "list", "query", "get_items", "list_items", "get_forecasts",
}


def _domain(entity_id):
    value = str(entity_id or "")
    return value.split(".", 1)[0] if "." in value else ""


def _entity_ids(value):
    """Extract only entity IDs, never arbitrary string values."""
    found = set()
    if isinstance(value, str):
        found.update(match.group(0).lower() for match in ENTITY_ID_RE.finditer(value))
    elif isinstance(value, list):
        for item in value:
            found.update(_entity_ids(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            found.update(_entity_ids(key))
            found.update(_entity_ids(item))
    return found


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)


def _identifiers(value):
    found = set()
    for text in _strings(value):
        found.update(IDENT_RE.findall(text))
    return found


def _collect_variable_definitions(obj):
    """Collect variable definitions from automation and nested action scopes.

    Multiple definitions of the same variable are retained as possible values.
    This is deliberate: static analysis must prefer safe over-approximation over
    pretending a single runtime branch is known.
    """
    definitions = defaultdict(list)

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        variables = value.get("variables")
        if isinstance(variables, dict):
            for name, definition in variables.items():
                definitions[str(name)].append(definition)
        for item in value.values():
            walk(item)

    walk(obj)
    return definitions


def resolve_variable_lineage(obj):
    """Return variable -> possible entity IDs without evaluating Jinja."""
    definitions = _collect_variable_definitions(obj)
    direct = {name: set() for name in definitions}
    refs = {name: set() for name in definitions}

    for name, values in definitions.items():
        for value in values:
            direct[name].update(_entity_ids(value))
            refs[name].update(identifier for identifier in _identifiers(value) if identifier != name)

    lineage = {name: set(values) for name, values in direct.items()}
    # Resolve chains such as next_clim -> next_item -> clims -> climate.*.
    for _ in range(12):
        changed = False
        for name in definitions:
            merged = set(lineage[name])
            for ref in refs[name]:
                merged.update(lineage.get(ref, ()))
            if merged != lineage[name]:
                lineage[name] = merged
                changed = True
        if not changed:
            break

    return lineage


def _is_read_only_action(action_name):
    value = str(action_name or "")
    if "." not in value:
        return False
    verb = value.split(".", 1)[1].lower()
    return (
        verb.startswith(("get_", "list_", "query_"))
        or verb in READ_ONLY_VERBS
    )


def _walk_action_nodes(obj):
    if isinstance(obj, list):
        for item in obj:
            yield from _walk_action_nodes(item)
        return
    if not isinstance(obj, dict):
        return

    action_name = obj.get("action") or obj.get("service")
    if isinstance(action_name, str):
        yield obj

    # Generic recursive walk supports choose/repeat/parallel/sequence/default
    # and future nested action containers without maintaining a fragile key list.
    for value in obj.values():
        if isinstance(value, (dict, list)):
            yield from _walk_action_nodes(value)


def _target_values(action):
    values = []
    target = action.get("target")
    if isinstance(target, dict) and "entity_id" in target:
        values.append(target.get("entity_id"))
    data = action.get("data")
    if isinstance(data, dict) and "entity_id" in data:
        values.append(data.get("entity_id"))
    if "entity_id" in action:
        values.append(action.get("entity_id"))
    return values


def _template_variable_names(value):
    if not isinstance(value, str) or not any(marker in value for marker in JINJA_MARKERS):
        return set()
    return set(IDENT_RE.findall(value))


def _resolve_target(value, lineage, action_domain, automation_entities):
    """Resolve action target to candidates and confidence.

    Returns (candidates, confidence, dynamic, variables, method).
    """
    direct = _entity_ids(value)
    dynamic = any(
        isinstance(text, str) and any(marker in text for marker in JINJA_MARKERS)
        for text in _strings(value)
    )
    variable_names = set()
    for text in _strings(value):
        variable_names.update(_template_variable_names(text))

    if not dynamic:
        return direct, (1.0 if direct else 0.0), False, variable_names, "static"

    candidates = set(direct)
    for name in variable_names:
        candidates.update(lineage.get(name, ()))

    if candidates:
        confidence = 0.90 if len(candidates) == 1 else 0.72
        method = "variable_lineage" if not direct else "template_literals"
        return candidates, confidence, True, variable_names, method

    # Conservative domain-based fallback. Example:
    # climate.set_hvac_mode target "{{ clim }}" where clim derives from
    # repeat.item.entity and the collection of possible climate entities is
    # visible elsewhere in automation variables.
    if action_domain:
        same_domain = {
            entity_id
            for entities in lineage.values()
            for entity_id in entities
            if _domain(entity_id) == action_domain
        }
        same_domain.update(
            entity_id for entity_id in automation_entities if _domain(entity_id) == action_domain
        )
        if 0 < len(same_domain) <= 16:
            return same_domain, 0.55, True, variable_names, "domain_inference"

    return set(), 0.0, True, variable_names, "unresolved"


def analyze_effective_automation(effective, alias="Automation", source="", blueprint=None):
    """Analyze one already-expanded automation definition."""
    lineage = resolve_variable_lineage(effective)
    automation_entities = _entity_ids(effective)

    controls = {}
    calls = {}
    unresolved = []
    target_attempts = 0
    resolved_attempts = 0
    dynamic_attempts = 0
    dynamic_resolved = 0
    action_count = 0

    for action in _walk_action_nodes(effective.get("actions", effective.get("action", []))):
        action_count += 1
        action_name = action.get("action") or action.get("service")
        action_name = str(action_name or "")
        if "." not in action_name:
            continue
        action_domain, action_verb = action_name.split(".", 1)

        # Direct script/scene/automation service name, e.g. script.notifier_x.
        if (
            action_domain in CALL_DOMAINS
            and action_verb not in {
                "turn_on", "turn_off", "toggle", "reload", "trigger",
            }
            and ENTITY_ID_RE.fullmatch(action_name)
        ):
            calls[action_name] = max(calls.get(action_name, 0.0), 1.0)

        for raw_target in _target_values(action):
            target_attempts += 1
            candidates, confidence, dynamic, variables, method = _resolve_target(
                raw_target, lineage, action_domain, automation_entities
            )
            if dynamic:
                dynamic_attempts += 1
            if candidates:
                resolved_attempts += 1
                if dynamic:
                    dynamic_resolved += 1
            elif dynamic:
                unresolved.append({
                    "action": action_name,
                    "variables": sorted(variables)[:8],
                    "method": method,
                })

            if _is_read_only_action(action_name):
                continue

            for entity_id in candidates:
                # A target entity from script/scene/automation is an invocation
                # edge, not a physical/helper control edge.
                if _domain(entity_id) in CALL_DOMAINS or action_domain in CALL_DOMAINS:
                    calls[entity_id] = max(calls.get(entity_id, 0.0), confidence)
                else:
                    controls[entity_id] = max(controls.get(entity_id, 0.0), confidence)

    return {
        "automation": alias,
        "source": source,
        "blueprint": blueprint,
        "action_count": action_count,
        "controls": [
            {"entity_id": entity_id, "confidence": round(confidence, 2)}
            for entity_id, confidence in sorted(controls.items())
        ],
        "calls": [
            {"entity_id": entity_id, "confidence": round(confidence, 2)}
            for entity_id, confidence in sorted(calls.items())
        ],
        "unresolved_dynamic_targets": unresolved[:12],
        "target_attempts": target_attempts,
        "resolved_target_attempts": resolved_attempts,
        "dynamic_target_attempts": dynamic_attempts,
        "dynamic_target_resolved": dynamic_resolved,
    }


def _looks_like_automation(item):
    if not isinstance(item, dict):
        return False
    if "use_blueprint" in item:
        return True
    has_trigger = any(key in item for key in ("trigger", "triggers"))
    has_action = any(key in item for key in ("action", "actions"))
    return has_trigger and has_action


def _collect_effective_automations(data, source, blueprint_registry):
    result = []

    def add_item(item, forced_alias=None):
        if not isinstance(item, dict) or not _looks_like_automation(item):
            return
        alias = forced_alias or item.get("alias") or item.get("name") or "Automation sans nom"
        effective = item
        blueprint_path = None
        if "use_blueprint" in item:
            use = item.get("use_blueprint")
            if isinstance(use, dict):
                blueprint_path = use.get("path")
            try:
                expanded, _error = core_scanner._expand_blueprint(item, blueprint_registry)
            except Exception:
                expanded = None
            if isinstance(expanded, dict):
                effective = expanded
        result.append((str(alias), effective, blueprint_path))

    def walk(value):
        if isinstance(value, list):
            for item in value:
                add_item(item)
            return
        if not isinstance(value, dict):
            return

        for key, item in value.items():
            if str(key) == "automation":
                if isinstance(item, list):
                    for candidate in item:
                        add_item(candidate)
                elif isinstance(item, dict):
                    for name, candidate in item.items():
                        add_item(candidate, forced_alias=str(name))
                continue

            if isinstance(item, (dict, list)) and str(key) != "blueprint":
                # Avoid traversing blueprint definitions as if they were active.
                if "blueprints" not in source.replace("\\", "/"):
                    walk(item)

    if isinstance(data, list):
        for item in data:
            add_item(item)
    else:
        walk(data)
    return result


def _load_source_documents(report):
    root = Path(core_scanner.CONFIG_ROOT)
    wanted = {
        str(node.get("source"))
        for node in (report.get("dependency_graph") or [])
        if node.get("source")
    }
    docs = {}
    errors = []

    paths = []
    for rel in sorted(wanted):
        path = root / rel
        if path.is_file():
            paths.append(path)

    blueprint_root = root / "blueprints" / "automation"
    if blueprint_root.exists():
        paths.extend(
            path for path in blueprint_root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
        )

    seen = set()
    for path in paths:
        try:
            rel = str(path.relative_to(root))
        except Exception:
            continue
        if rel in seen:
            continue
        seen.add(rel)
        try:
            if not core_scanner._should_read(path):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            docs[rel] = yaml.load(text, Loader=core_scanner.HALoader)
        except Exception as exc:
            errors.append({"file": rel, "error": type(exc).__name__})
    return docs, errors


def enrich_dependency_graph(report):
    """Upgrade 0.7 graph to semantic entity-flow V3."""
    docs, parse_errors = _load_source_documents(report)
    try:
        blueprint_registry = core_scanner._build_blueprint_registry(docs)
    except Exception:
        blueprint_registry = {}

    flow_by_key = defaultdict(list)
    for source, data in docs.items():
        if "blueprints/automation/" in source.replace("\\", "/"):
            continue
        for alias, effective, blueprint_path in _collect_effective_automations(
            data, source, blueprint_registry
        ):
            flow_by_key[(source, alias)].append(
                analyze_effective_automation(
                    effective, alias=alias, source=source, blueprint=blueprint_path
                )
            )

    before_meta = dict(report.get("dependency_graph_meta") or {})
    total_attempts = 0
    resolved_attempts = 0
    dynamic_attempts = 0
    dynamic_resolved = 0
    call_edges = 0
    control_edges = 0
    possible_control_edges = 0
    unresolved_targets = 0
    matched_nodes = 0
    graph = []

    for raw in report.get("dependency_graph") or []:
        node = dict(raw)
        source = str(node.get("source") or "")
        alias = str(node.get("automation") or "")
        candidates = flow_by_key.get((source, alias), [])
        semantic = candidates.pop(0) if candidates else None
        if semantic:
            matched_nodes += 1

        existing_controls = set(node.get("controls") or [])
        existing_calls = {
            entity_id
            for entity_id in existing_controls
            if _domain(entity_id) in CALL_DOMAINS
        }
        existing_controls -= existing_calls

        dynamic_controls = {}
        semantic_calls = {entity_id: 1.0 for entity_id in existing_calls}
        unresolved = []

        if semantic:
            total_attempts += int(semantic.get("target_attempts", 0))
            resolved_attempts += int(semantic.get("resolved_target_attempts", 0))
            dynamic_attempts += int(semantic.get("dynamic_target_attempts", 0))
            dynamic_resolved += int(semantic.get("dynamic_target_resolved", 0))
            unresolved = list(semantic.get("unresolved_dynamic_targets") or [])

            for item in semantic.get("controls") or []:
                entity_id = str(item.get("entity_id") or "")
                confidence = float(item.get("confidence", 0) or 0)
                if not entity_id:
                    continue
                existing_controls.add(entity_id)
                if confidence < 0.999:
                    dynamic_controls[entity_id] = max(
                        dynamic_controls.get(entity_id, 0.0), confidence
                    )
            for item in semantic.get("calls") or []:
                entity_id = str(item.get("entity_id") or "")
                confidence = float(item.get("confidence", 0) or 0)
                if entity_id:
                    semantic_calls[entity_id] = max(
                        semantic_calls.get(entity_id, 0.0), confidence
                    )

        refs = set(node.get("references") or [])
        triggers = set(node.get("triggers_on") or [])
        refs.update(existing_controls)
        refs.update(semantic_calls)
        reads = refs - triggers - existing_controls - set(semantic_calls)

        node["controls"] = sorted(existing_controls)
        node["calls"] = sorted(semantic_calls)
        node["reads"] = sorted(reads)
        node["references"] = sorted(refs)
        node["entities"] = sorted(refs | triggers | existing_controls | set(semantic_calls))
        node["dynamic_controls"] = [
            {"entity_id": entity_id, "confidence": round(confidence, 2)}
            for entity_id, confidence in sorted(dynamic_controls.items())
        ]
        node["unresolved_dynamic_targets"] = unresolved
        node["semantic_flow_matched"] = bool(semantic)
        graph.append(node)

        control_edges += len(existing_controls)
        call_edges += len(semantic_calls)
        possible_control_edges += sum(
            1 for confidence in dynamic_controls.values() if confidence < 0.85
        )
        unresolved_targets += len(unresolved)

    resolution_rate = (
        round(resolved_attempts / total_attempts, 3) if total_attempts else 1.0
    )
    dynamic_resolution_rate = (
        round(dynamic_resolved / dynamic_attempts, 3) if dynamic_attempts else 1.0
    )

    report["dependency_graph"] = graph
    report["dependency_graph_meta"] = {
        **before_meta,
        "model": MODEL,
        "automation_nodes": len(graph),
        "semantic_nodes_matched": matched_nodes,
        "semantic_match_rate": round(matched_nodes / len(graph), 3) if graph else 1.0,
        "target_attempts": total_attempts,
        "resolved_target_attempts": resolved_attempts,
        "target_resolution_rate": resolution_rate,
        "dynamic_target_attempts": dynamic_attempts,
        "dynamic_target_resolved": dynamic_resolved,
        "dynamic_target_resolution_rate": dynamic_resolution_rate,
        "unresolved_dynamic_target_count": unresolved_targets,
        "control_edges": control_edges,
        "call_edges": call_edges,
        "possible_control_edges": possible_control_edges,
        "entity_edges": sum(len(node.get("entities") or []) for node in graph),
        "flow_reparse_errors": parse_errors[:12],
        "raw_yaml_persisted": False,
        "dynamic_template_text_persisted": False,
        "service_calls_are_entities": False,
    }
    return graph
