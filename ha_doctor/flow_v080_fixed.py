"""HA Doctor 0.8 semantic-flow hardening patch.

Keeps Entity Flow V3 backward compatible while fixing two edge cases found by
CI before release:
1. Home Assistant service names such as switch.turn_on must never be inferred
   as entity targets during dynamic domain fallback.
2. An explicit automation alias wins over a package mapping key.

The base flow module functions use module globals at runtime, so patching the
helpers here also hardens enrich_dependency_graph without duplicating the full
engine.
"""

import flow_v080 as _base
import intelligence_v070 as _v070

VERSION = "0.8.0"
MODEL = _base.MODEL

_original_entity_ids = _base._entity_ids


def _entity_ids_without_services(value):
    values = _original_entity_ids(value)
    cleaned = set()
    for entity_id in values:
        text = str(entity_id or "")
        if "." not in text:
            continue
        _domain, object_id = text.split(".", 1)
        if object_id in _v070.SERVICE_OBJECTS:
            continue
        cleaned.add(text)
    return cleaned


# Harden every existing base function that calls _entity_ids dynamically.
_base._entity_ids = _entity_ids_without_services


def _collect_effective_automations_fixed(data, source, blueprint_registry):
    result = []

    def add_item(item, forced_alias=None):
        if not isinstance(item, dict) or not _base._looks_like_automation(item):
            return
        # Explicit alias/name is authoritative; mapping key is only a fallback.
        alias = item.get("alias") or item.get("name") or forced_alias or "Automation sans nom"
        effective = item
        blueprint_path = None
        if "use_blueprint" in item:
            use = item.get("use_blueprint")
            if isinstance(use, dict):
                blueprint_path = use.get("path")
            try:
                expanded, _error = _base.core_scanner._expand_blueprint(
                    item, blueprint_registry
                )
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
                if "blueprints" not in source.replace("\\", "/"):
                    walk(item)

    if isinstance(data, list):
        for item in data:
            add_item(item)
    else:
        walk(data)
    return result


_base._collect_effective_automations = _collect_effective_automations_fixed

# Public re-exports used by scanner/tests.
resolve_variable_lineage = _base.resolve_variable_lineage
analyze_effective_automation = _base.analyze_effective_automation
enrich_dependency_graph = _base.enrich_dependency_graph
