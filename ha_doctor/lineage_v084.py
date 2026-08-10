"""HA Doctor 0.8.4 entity-lineage and indirect blast-radius analysis.

Builds a conservative graph:
    source entity -> derived template entity -> automation

Only active YAML files are read. secrets.yaml, .storage, backups, archives and
binary/certificate files remain excluded. Raw YAML and state values are never
persisted in the report.
"""
from collections import defaultdict, deque
from pathlib import Path
import re
import unicodedata

import yaml

import scanner
import impact_v083

VERSION = "0.8.4"
LINEAGE_MODEL = "entity_lineage_v1"
BLAST_MODEL = "registry_blast_radius_v4_lineage"
MAX_EDGES = 1200
MAX_PARSE_ERRORS = 20
MAX_PATHS = 24
DERIVED_DOMAINS = {"sensor", "binary_sensor", "number", "select", "text"}
_ARCHIVE_PARTS = {"archive", "archives", "old", "obsolete", "deprecated"}
_BACKUP_RE = re.compile(r"(?:^|[_\-.])(backup|bak|copy|old)(?:[_\-.]|$)", re.I)


def _slug(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _known_entities(report):
    known = set()
    for node in report.get("dependency_graph") or []:
        for key in (
            "controls", "triggers_on", "references", "reads", "calls",
            "transitive_controls", "transitive_calls",
        ):
            known.update(str(x) for x in node.get(key) or [] if x)
        for item in node.get("dynamic_controls") or []:
            if item.get("entity_id"):
                known.add(str(item["entity_id"]))
    registry = report.get("registry_analysis") or {}
    for container in (
        (registry.get("integration_health") or {}).get("groups") or [],
        (registry.get("device_health") or {}).get("groups") or [],
    ):
        for group in container:
            known.update(str(x) for x in group.get("affected_entities") or [] if x)
            known.update(str(x) for x in group.get("examples") or [] if x)
    for finding in report.get("findings") or []:
        for example in finding.get("examples") or []:
            if isinstance(example, dict) and example.get("entity_id"):
                known.add(str(example["entity_id"]))
    return known


def _active_yaml(path):
    try:
        if not scanner._should_read(path):
            return False
        rel = path.relative_to(scanner.CONFIG_ROOT)
    except Exception:
        return False
    parts = {part.lower() for part in rel.parts}
    if parts & _ARCHIVE_PARTS:
        return False
    if "blueprints" in parts:
        return False
    if _BACKUP_RE.search(path.stem):
        return False
    return True


def _entity_sources(value):
    try:
        return set(scanner._extract_entities(value))
    except Exception:
        return set()


def _modern_blocks(doc, path):
    """Yield modern template blocks without assuming a specific include style."""
    if isinstance(doc, dict) and "template" in doc:
        raw = doc.get("template")
        if isinstance(raw, list):
            for block in raw:
                if isinstance(block, dict):
                    yield block
        elif isinstance(raw, dict):
            yield raw
    if path.name.lower() in {"templates.yaml", "templates.yml", "template.yaml", "template.yml"}:
        if isinstance(doc, list):
            for block in doc:
                if isinstance(block, dict):
                    yield block
        elif isinstance(doc, dict) and "template" not in doc:
            yield doc


def _definition_items(raw):
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                yield None, item
    elif isinstance(raw, dict):
        for key, item in raw.items():
            if isinstance(item, dict):
                yield str(key), item


def _infer_output(domain, key, definition, known):
    candidates = []
    if key:
        candidates.append(f"{domain}.{_slug(key)}")
    name = definition.get("name") if isinstance(definition, dict) else None
    if isinstance(name, str) and "{{" not in name and "{%" not in name:
        candidates.append(f"{domain}.{_slug(name)}")
    unique = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    for candidate in unique:
        if candidate in known:
            return candidate, 1.0, "confirmed_in_effective_graph"
    if unique:
        return unique[0], 0.72, "name_slug_inference"
    return None, 0.0, "output_not_inferable"


def _modern_edges(doc, path, known):
    for block in _modern_blocks(doc, path):
        for domain in DERIVED_DOMAINS:
            raw = block.get(domain)
            if raw is None:
                continue
            for key, definition in _definition_items(raw):
                output, confidence, reason = _infer_output(domain, key, definition, known)
                if not output:
                    yield None, {
                        "file": str(path.relative_to(scanner.CONFIG_ROOT)),
                        "domain": domain,
                        "reason": reason,
                    }
                    continue
                sources = sorted(_entity_sources(definition) - {output})
                for source in sources:
                    yield {
                        "source": source,
                        "derived": output,
                        "confidence": confidence,
                        "confidence_reason": reason,
                        "file": str(path.relative_to(scanner.CONFIG_ROOT)),
                    }, None


def _legacy_edges(doc, path, known):
    if not isinstance(doc, dict):
        return
    raw_sensor = doc.get("sensor")
    entries = raw_sensor if isinstance(raw_sensor, list) else []
    for platform in entries:
        if not isinstance(platform, dict) or str(platform.get("platform") or "").lower() != "template":
            continue
        sensors = platform.get("sensors")
        if not isinstance(sensors, dict):
            continue
        for key, definition in sensors.items():
            if not isinstance(definition, dict):
                continue
            output = f"sensor.{_slug(key)}"
            confidence = 1.0 if output in known else 0.85
            reason = "legacy_object_id" if output in known else "legacy_object_id_unconfirmed"
            for source in sorted(_entity_sources(definition) - {output}):
                yield {
                    "source": source,
                    "derived": output,
                    "confidence": confidence,
                    "confidence_reason": reason,
                    "file": str(path.relative_to(scanner.CONFIG_ROOT)),
                }


def build_entity_lineage_v1(report):
    known = _known_entities(report)
    edges = []
    unresolved = []
    parse_errors = []
    root = Path(scanner.CONFIG_ROOT)
    if root.exists():
        for path in sorted(root.rglob("*")):
            if len(edges) >= MAX_EDGES:
                break
            if not path.is_file() or not _active_yaml(path):
                continue
            try:
                if path.stat().st_size > scanner.MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                doc = yaml.load(text, Loader=scanner.HALoader)
            except Exception as exc:
                if len(parse_errors) < MAX_PARSE_ERRORS:
                    parse_errors.append({
                        "file": str(path.relative_to(root)),
                        "error": type(exc).__name__,
                    })
                continue

            try:
                for edge, missing in _modern_edges(doc, path, known):
                    if edge and len(edges) < MAX_EDGES:
                        edges.append(edge)
                    if missing and len(unresolved) < 60:
                        unresolved.append(missing)
                for edge in _legacy_edges(doc, path, known) or []:
                    if len(edges) < MAX_EDGES:
                        edges.append(edge)
            except Exception as exc:
                if len(parse_errors) < MAX_PARSE_ERRORS:
                    parse_errors.append({
                        "file": str(path.relative_to(root)),
                        "error": f"lineage:{type(exc).__name__}",
                    })

    best = {}
    for edge in edges:
        key = (edge["source"], edge["derived"])
        current = best.get(key)
        if current is None or float(edge.get("confidence", 0)) > float(current.get("confidence", 0)):
            best[key] = edge
    edges = sorted(best.values(), key=lambda item: (item["source"], item["derived"]))

    confirmed = [
        edge for edge in edges
        if float(edge.get("confidence", 0) or 0) >= 0.85
        and (edge.get("derived") in known)
    ]
    result = {
        "model": LINEAGE_MODEL,
        "edge_count": len(edges),
        "confirmed_edge_count": len(confirmed),
        "source_entity_count": len({edge["source"] for edge in edges}),
        "derived_entity_count": len({edge["derived"] for edge in edges}),
        "known_entity_count": len(known),
        "unresolved_output_count": len(unresolved),
        "parse_error_count": len(parse_errors),
        "edges": edges[:350],
        "unresolved_outputs": unresolved[:30],
        "parse_errors": parse_errors,
        "raw_yaml_persisted": False,
        "secret_values_persisted": False,
        "max_depth_for_blast_radius": 4,
        "interpretation": (
            "Le lineage relie uniquement des dépendances de templates observables statiquement. "
            "Les sorties inférées par nom ne servent au blast radius que lorsqu'elles sont "
            "confirmées dans le graphe Home Assistant effectif."
        ),
    }
    report["entity_lineage"] = result
    report.setdefault("privacy", {}).update({
        "entity_lineage_raw_yaml_persisted": False,
        "entity_lineage_secret_values_persisted": False,
    })
    report.setdefault("diagnostic_engine", {})["entity_lineage"] = True
    return result


def _lineage_adjacency(report):
    adjacency = defaultdict(set)
    known = _known_entities(report)
    for edge in (report.get("entity_lineage") or {}).get("edges") or []:
        if (
            float(edge.get("confidence", 0) or 0) >= 0.85
            and edge.get("source")
            and edge.get("derived") in known
        ):
            adjacency[str(edge["source"])].add(str(edge["derived"]))
    return adjacency


def expand_lineage(report, seeds, max_depth=4):
    adjacency = _lineage_adjacency(report)
    seeds = {str(x) for x in seeds or [] if x}
    seen = set(seeds)
    derived = set()
    paths = []
    queue = deque((seed, [seed], 0) for seed in sorted(seeds))
    while queue:
        current, path, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for nxt in sorted(adjacency.get(current) or ()):
            if nxt not in seen:
                seen.add(nxt)
                derived.add(nxt)
                next_path = path + [nxt]
                if len(paths) < MAX_PATHS:
                    paths.append(next_path)
                queue.append((nxt, next_path, depth + 1))
    return seen, derived, paths


def apply_registry_lineage_blast_radius_v4(report):
    if not report.get("entity_lineage"):
        build_entity_lineage_v1(report)

    explanations = report.get("diagnostic_explanations") or []
    by_id = {}
    impacted_all = set()
    levels = defaultdict(int)
    lineage_incidents = 0

    for item in explanations:
        if not str(item.get("source_type") or "").startswith("registry_"):
            continue
        direct = impact_v083._registry_entities(report, item)
        expanded, derived, paths = expand_lineage(report, direct)
        impact = impact_v083._impact_for_entities(report, expanded)
        impact["model"] = BLAST_MODEL
        impact["direct_entity_match_count"] = len(direct)
        impact["lineage_derived_entity_count"] = len(derived)
        impact["lineage_used"] = bool(derived)
        impact["lineage_paths"] = [{"path": path} for path in paths[:10]]
        if derived:
            lineage_incidents += 1
        item["dependency_impact"] = impact
        diagnostic_id = str(item.get("id") or "")
        if diagnostic_id:
            by_id[diagnostic_id] = impact
        impacted_all.update(impact.get("impacted_automations") or [])
        levels[str(impact.get("level") or "none")] += 1

    for section_name in ("action_plan", "recommendation_queue"):
        section = report.get(section_name) or {}
        for item in section.get("items") or []:
            diagnostic_id = str(item.get("id") or "")
            if diagnostic_id in by_id:
                item["dependency_impact"] = dict(by_id[diagnostic_id])

    root = report.setdefault("root_cause_summary", {})
    root.update({
        "registry_blast_radius_model": BLAST_MODEL,
        "registry_impacted_automation_count": len(impacted_all),
        "registry_blast_radius_levels": dict(levels),
        "registry_high_or_critical_incident_count": (
            levels.get("high", 0) + levels.get("critical", 0)
        ),
        "registry_lineage_incident_count": lineage_incidents,
    })
    report.setdefault("diagnostic_engine", {})["registry_blast_radius_v4_lineage"] = True
    return root
