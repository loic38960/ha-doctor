"""HA Doctor 0.8.3 flow confidence and controller-risk calibration."""
from collections import Counter
import re

import intelligence_v080 as architecture_base
import semantics_v081 as sem_base
import semantics_v082 as base

VERSION = "0.8.3"
FLOW_MODEL = "flow_confidence_v3"
CONDITION_MODEL = "condition_semantics_v3"


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


_ENTITY_LITERAL_RE = re.compile(r"\b[a-z_][a-z0-9_]*\.[A-Za-z0-9_]+\b")


def _literal_entity_ids(effective):
    """Collect literal entity-like identifiers from the effective automation.

    We only use this set to confirm an entity already proposed by Entity Flow,
    so service names that also match ``domain.object`` cannot create new targets.
    """
    found = set()
    for text in _strings(effective):
        if isinstance(text, str):
            found.update(_ENTITY_LITERAL_RE.findall(text))
    return found


def build_flow_confidence_v3(report):
    by_alias, _ = sem_base.effective_automation_map(report)
    graph = report.get("dependency_graph") or []
    promoted = 0
    confidences = []

    for node in graph:
        alias = str(node.get("automation") or "")
        records = by_alias.get(alias) or []
        literals = set()
        if len(records) == 1:
            literals = _literal_entity_ids(records[0].get("effective") or {})
        for item in node.get("dynamic_controls") or []:
            entity_id = str(item.get("entity_id") or "")
            try:
                confidence = float(item.get("confidence", 0) or 0)
            except Exception:
                confidence = 0.0
            if entity_id and entity_id in literals and confidence < 0.90:
                confidence = 0.90
                item["confidence"] = confidence
                item["confidence_reason"] = "literal_entity_confirmed_in_effective_yaml"
                promoted += 1
            confidences.append(confidence)

    bands = {
        "high": sum(1 for value in confidences if value >= 0.85),
        "inferred": sum(1 for value in confidences if 0.60 <= value < 0.85),
        "heuristic": sum(1 for value in confidences if 0 < value < 0.60),
    }
    review_required = sum(1 for value in confidences if 0 < value < 0.70)
    total = len(confidences)
    review_ratio = review_required / total if total else 0.0
    meta = report.setdefault("dependency_graph_meta", {})
    unresolved = int(meta.get("unresolved_dynamic_target_count", 0) or 0)

    if unresolved:
        quality = "fail"
    elif review_ratio >= 0.25:
        quality = "warning"
    else:
        quality = "pass"

    result = {
        "model": FLOW_MODEL,
        "target_resolution_rate": float(meta.get("target_resolution_rate", 1.0) or 0),
        "dynamic_target_resolution_rate": float(meta.get("dynamic_target_resolution_rate", 1.0) or 0),
        "static_control_edges": max(0, int(meta.get("control_edges", 0) or 0) - total),
        "dynamic_control_edges": total,
        "dynamic_confidence_bands": bands,
        "literal_confirmed_promotions": promoted,
        "review_required_dynamic_edges": review_required,
        "review_required_ratio": round(review_ratio, 3),
        "low_confidence_dynamic_edges": bands["heuristic"],
        "low_confidence_ratio": round(review_ratio, 3),
        "unresolved_dynamic_targets": unresolved,
        "quality_status": quality,
        "interpretation": (
            "V3 distingue les cibles dynamiques simplement inférées des cibles réellement "
            "heuristiques. Une cible littérale retrouvée dans le YAML effectif est promue "
            "sans prétendre exécuter le template."
        ),
    }
    report["flow_confidence"] = result
    meta.update({
        "confidence_model": FLOW_MODEL,
        "dynamic_control_confidence": bands,
        "literal_confirmed_dynamic_edges": promoted,
        "review_required_dynamic_edges": review_required,
        "low_confidence_ratio": result["low_confidence_ratio"],
    })
    return result


def _pair_intent(by_alias, alias, target):
    records = by_alias.get(alias) or []
    if len(records) != 1:
        return set()
    try:
        return base._deterministic_intents(records[0].get("effective") or {}, target)
    except Exception:
        return set()


def build_condition_semantics_v3(report):
    current = report.get("condition_semantics") or {}
    by_alias, parse_errors = sem_base.effective_automation_map(report)
    unresolved = []
    contradictory = []
    helper_pairs = []
    physical_pairs = []
    optional_pairs = []

    for pair in current.get("unproven_pairs") or []:
        target = str(pair.get("entity_id") or "")
        automations = [str(x) for x in pair.get("automations") or []]
        kind = architecture_base._kind(target)
        enriched = {**pair, "target_kind": kind}
        if len(automations) == 2:
            a_intent = _pair_intent(by_alias, automations[0], target)
            b_intent = _pair_intent(by_alias, automations[1], target)
            if len(a_intent) == 1 and len(b_intent) == 1 and a_intent != b_intent:
                enriched["conflict_evidence"] = {
                    "kind": "opposite_or_different_deterministic_commands",
                    "intent_a": sorted(a_intent),
                    "intent_b": sorted(b_intent),
                }
                enriched["review_priority"] = "high"
                contradictory.append(enriched)
        if "review_priority" not in enriched:
            enriched["review_priority"] = "high" if kind == "actuator" else ("low" if kind == "helper" else "medium")
        unresolved.append(enriched)
        if kind == "actuator":
            physical_pairs.append(enriched)
        elif kind == "helper":
            helper_pairs.append(enriched)
        else:
            optional_pairs.append(enriched)

    result = {
        **current,
        "model": CONDITION_MODEL,
        "unproven_pairs": unresolved[:60],
        "unproven_pair_count": len(unresolved),
        "physical_unproven_pair_count": len(physical_pairs),
        "helper_unproven_pair_count": len(helper_pairs),
        "other_unproven_pair_count": len(optional_pairs),
        "contradictory_deterministic_pair_count": len(contradictory),
        "contradictory_deterministic_pairs": contradictory[:20],
        "parse_errors": (current.get("parse_errors") or parse_errors or [])[:12],
        "confidence": "high_for_resolved_and_deterministic_conflicts",
        "note": (
            "V3 sépare les conflits potentiels sur actionneurs physiques des écritures de "
            "helpers et met en avant les commandes déterministes réellement divergentes."
        ),
    }
    report["condition_semantics"] = result

    arch = report.setdefault("architecture_analysis", {})
    arch.update({
        "condition_semantics_model": CONDITION_MODEL,
        "physical_unproven_controller_pair_count": len(physical_pairs),
        "helper_unproven_controller_pair_count": len(helper_pairs),
        "contradictory_deterministic_pair_count": len(contradictory),
    })

    finding = next((x for x in report.get("findings") or [] if x.get("rule_id") == "HD-AUTO-003"), None)
    if finding:
        finding["summary"] = (
            f"{len(physical_pairs)} paire(s) sur actionneur physique restent à vérifier, "
            f"{len(helper_pairs)} paire(s) concernent seulement des helpers et "
            f"{int(current.get('resolved_pair_count', 0) or 0)} paire(s) sont déjà résolues."
        )
        finding["recommendation"] = (
            "Traiter d'abord les paires sur actionneurs physiques, surtout lorsqu'une "
            "commande déterministe divergente est démontrée. Les helpers passent après."
        )

    for explanation in report.get("diagnostic_explanations") or []:
        if str(explanation.get("source_id") or "") != "HD-AUTO-003":
            continue
        explanation["diagnosis"] = (
            f"{len(physical_pairs)} paire(s) physique(s) et {len(helper_pairs)} paire(s) "
            f"de helpers restent non prouvées ; {len(contradictory)} divergence(s) "
            "déterministe(s) sont explicitement identifiées."
        )
        explanation["why_now"] = (
            "Priorité dirigée vers les actionneurs physiques et les commandes divergentes, "
            "pas vers le simple fan-out de helpers."
        )

    return result
