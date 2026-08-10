"""HA Doctor 0.8.1 flow-confidence and condition-semantics helpers."""

from collections import defaultdict
import re

import scanner as core_scanner
import flow_v080 as flow

VERSION = "0.8.1"

_IS_STATE_RE = re.compile(
    r"is_state\(\s*['\"](?P<entity>[a-z0-9_]+\.[a-z0-9_]+)['\"]\s*,\s*['\"](?P<state>[^'\"]+)['\"]\s*\)",
    re.IGNORECASE,
)
_STATES_EQ_RE = re.compile(
    r"states\(\s*['\"](?P<entity>[a-z0-9_]+\.[a-z0-9_]+)['\"]\s*\)\s*==\s*['\"](?P<state>[^'\"]+)['\"]",
    re.IGNORECASE,
)


def build_flow_confidence(report):
    graph = report.get("dependency_graph") or []
    meta = report.setdefault("dependency_graph_meta", {})
    confidences = []
    for node in graph:
        for item in node.get("dynamic_controls") or []:
            try:
                value = float(item.get("confidence", 0) or 0)
            except Exception:
                value = 0.0
            if value > 0:
                confidences.append(value)

    bands = {
        "high": sum(1 for value in confidences if value >= 0.85),
        "inferred": sum(1 for value in confidences if 0.60 <= value < 0.85),
        "heuristic": sum(1 for value in confidences if 0 < value < 0.60),
    }
    dynamic_edges = len(confidences)
    static_edges = max(0, int(meta.get("control_edges", 0) or 0) - dynamic_edges)
    low_edges = bands["inferred"] + bands["heuristic"]

    result = {
        "model": "flow_confidence_v1",
        "target_resolution_rate": float(meta.get("target_resolution_rate", 1.0) or 0),
        "dynamic_target_resolution_rate": float(meta.get("dynamic_target_resolution_rate", 1.0) or 0),
        "static_control_edges": static_edges,
        "dynamic_control_edges": dynamic_edges,
        "dynamic_confidence_bands": bands,
        "low_confidence_dynamic_edges": low_edges,
        "unresolved_dynamic_targets": int(meta.get("unresolved_dynamic_target_count", 0) or 0),
        "interpretation": (
            "Résolu ne signifie pas certain : les cibles dynamiques sont séparées en "
            "forte confiance, inférées et heuristiques."
        ),
    }
    report["flow_confidence"] = result
    meta.update({
        "confidence_model": result["model"],
        "static_control_edges": static_edges,
        "dynamic_control_edge_count": dynamic_edges,
        "dynamic_control_confidence": bands,
        "low_confidence_dynamic_edges": low_edges,
    })
    return result


def _merge_guards(target, source):
    for entity_id, states in source.items():
        target[entity_id].update(states)


def _template_guards(text):
    result = defaultdict(set)
    if not isinstance(text, str):
        return result
    lowered = text.lower()
    # OR/NOT cannot safely be promoted to mandatory guards.
    if " or " in lowered or " not " in lowered:
        return result
    for regex in (_IS_STATE_RE, _STATES_EQ_RE):
        for match in regex.finditer(text):
            result[match.group("entity").lower()].add(match.group("state"))
    return result


def required_state_guards(value):
    """Return only conditions that are provably mandatory (simple AND cases)."""
    guards = defaultdict(set)
    if isinstance(value, str):
        _merge_guards(guards, _template_guards(value))
        return dict(guards)
    if isinstance(value, list):
        for item in value:
            _merge_guards(guards, required_state_guards(item))
        return dict(guards)
    if not isinstance(value, dict):
        return {}

    kind = str(value.get("condition") or "").lower()
    if kind in {"or", "not"}:
        return {}
    if kind == "state":
        entities = flow._entity_ids(value.get("entity_id"))
        states = value.get("state")
        if not isinstance(states, list):
            states = [states] if states is not None else []
        for entity_id in entities:
            for state in states:
                if isinstance(state, (str, int, float, bool)):
                    guards[entity_id].add(str(state))
        return dict(guards)
    if kind == "and":
        _merge_guards(guards, required_state_guards(value.get("conditions") or []))
        return dict(guards)

    if "conditions" in value:
        _merge_guards(guards, required_state_guards(value.get("conditions")))
    for item in value.values():
        if isinstance(item, str):
            _merge_guards(guards, _template_guards(item))
    return dict(guards)


def effective_automation_map(report):
    docs, parse_errors = flow._load_source_documents(report)
    try:
        registry = core_scanner._build_blueprint_registry(docs)
    except Exception:
        registry = {}
    by_alias = defaultdict(list)
    for source, data in docs.items():
        if "blueprints/automation/" in source.replace("\\", "/"):
            continue
        try:
            items = flow._collect_effective_automations(data, source, registry)
        except Exception:
            continue
        for alias, effective, blueprint_path in items:
            conditions = effective.get("conditions", effective.get("condition", []))
            by_alias[str(alias)].append({
                "source": source,
                "effective": effective,
                "blueprint": blueprint_path,
                "guards": required_state_guards(conditions),
            })
    return by_alias, parse_errors


def _exclusive(guards_a, guards_b):
    evidence = []
    for entity_id in sorted(set(guards_a) & set(guards_b)):
        states_a = set(guards_a.get(entity_id) or ())
        states_b = set(guards_b.get(entity_id) or ())
        if states_a and states_b and states_a.isdisjoint(states_b):
            evidence.append({
                "entity_id": entity_id,
                "states_a": sorted(states_a),
                "states_b": sorted(states_b),
            })
    return evidence


def build_condition_semantics(report):
    by_alias, parse_errors = effective_automation_map(report)
    finding = next(
        (item for item in report.get("findings") or [] if item.get("rule_id") == "HD-AUTO-003"),
        None,
    )
    proven = []
    unresolved = []
    analyzed = 0

    if finding:
        refined = []
        for raw_example in finding.get("examples") or []:
            example = dict(raw_example)
            remaining = []
            local_proven = []
            for pair in example.get("unprotected_pairs") or []:
                if not isinstance(pair, list) or len(pair) != 2:
                    remaining.append(pair)
                    continue
                a, b = str(pair[0]), str(pair[1])
                analyzed += 1
                records_a = by_alias.get(a) or []
                records_b = by_alias.get(b) or []
                evidence = []
                if len(records_a) == 1 and len(records_b) == 1:
                    evidence = _exclusive(records_a[0]["guards"], records_b[0]["guards"])
                if evidence:
                    item = {
                        "entity_id": example.get("entity_id"),
                        "automations": [a, b],
                        "evidence": evidence,
                    }
                    proven.append(item)
                    local_proven.append(item)
                else:
                    remaining.append(pair)
                    unresolved.append({
                        "entity_id": example.get("entity_id"),
                        "automations": [a, b],
                    })
            example["unprotected_pairs"] = remaining
            example["unprotected_pair_count"] = len(remaining)
            example["proven_exclusive_pair_count"] = len(local_proven)
            if local_proven:
                example["proven_exclusive_pairs"] = local_proven
            if remaining or not local_proven:
                refined.append(example)

        finding["examples"] = refined
        finding["summary"] = (
            f"{len(refined)} entité(s) gardent au moins une paire de contrôleurs sans "
            f"exclusivité démontrée. {len(proven)} paire(s) ont été écartées par "
            "conditions d'état mutuellement exclusives."
        )
        finding["recommendation"] = (
            "Examiner uniquement les paires restantes. Les exclusivités prouvées par "
            "des conditions AND simples ne sont plus présentées comme conflits."
        )

    result = {
        "model": "condition_semantics_v1",
        "automation_count_with_required_state_guards": sum(
            1 for records in by_alias.values()
            if len(records) == 1 and records[0].get("guards")
        ),
        "controller_pairs_analyzed": analyzed,
        "proven_exclusive_pair_count": len(proven),
        "unproven_pair_count": len(unresolved),
        "proven_exclusive_pairs": proven[:30],
        "unproven_pairs": unresolved[:30],
        "parse_errors": parse_errors[:12],
        "confidence": "high_for_proven_exclusive_only",
        "note": (
            "Les OR, NOT et templates ambigus ne servent jamais à prouver une exclusivité."
        ),
    }
    report["condition_semantics"] = result

    architecture = report.get("architecture_analysis") or {}
    architecture["condition_semantics_model"] = result["model"]
    architecture["proven_exclusive_controller_pair_count"] = len(proven)
    architecture["unproven_controller_pair_count"] = len(unresolved)

    for explanation in report.get("diagnostic_explanations") or []:
        if str(explanation.get("source_id") or "") != "HD-AUTO-003":
            continue
        explanation["diagnosis"] = (
            f"HA Doctor a démontré {len(proven)} paire(s) de contrôleurs mutuellement "
            f"exclusives ; {len(unresolved)} paire(s) restent à vérifier."
        )
        if proven:
            evidence = list(explanation.get("evidence") or [])
            evidence.append({
                "type": "condition_semantics",
                "label": "Exclusivités démontrées",
                "text": f"{len(proven)} paire(s) écartées automatiquement",
            })
            explanation["evidence"] = evidence[:12]
    return result
