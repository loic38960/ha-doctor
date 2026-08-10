"""HA Doctor 0.8.4 semantic calibration.

Fixes post-promotion flow metadata, recomputes architecture from final flow
confidence and detects high-confidence multi-automation phase handoffs.
"""
import intelligence_v080 as architecture_base
import semantics_v081 as sem_v1
import semantics_v082 as sem_v2

VERSION = "0.8.4"
FLOW_MODEL = "flow_confidence_v3.1"
ARCH_MODEL = "architecture_v3_post_flow"
CONDITION_MODEL = "condition_semantics_v4_protocols"


def normalize_flow_metadata_v31(report):
    flow = report.get("flow_confidence") or {}
    meta = report.setdefault("dependency_graph_meta", {})
    bands = flow.get("dynamic_confidence_bands") or {}
    meta.update({
        "confidence_model": FLOW_MODEL,
        "dynamic_control_confidence": dict(bands),
        "low_confidence_dynamic_edges": int(flow.get("low_confidence_dynamic_edges", 0) or 0),
        "low_confidence_ratio": float(flow.get("low_confidence_ratio", 0) or 0),
        "review_required_dynamic_edges": int(flow.get("review_required_dynamic_edges", 0) or 0),
        "literal_confirmed_dynamic_edges": int(flow.get("literal_confirmed_promotions", 0) or 0),
    })
    flow["model"] = FLOW_MODEL
    flow["metadata_synchronized"] = True
    report["flow_confidence"] = flow
    return flow


def recompute_architecture_post_flow(report):
    previous = report.get("architecture_analysis") or {}
    result = architecture_base.build_architecture_v2(report)
    result = report.get("architecture_analysis") or result or {}
    result["model"] = ARCH_MODEL
    result["post_flow_recomputed"] = True
    result["flow_confidence_model"] = (report.get("flow_confidence") or {}).get("model")
    result["previous_model"] = previous.get("model")
    report["architecture_analysis"] = result
    return result


def _node_map(report):
    return {
        str(node.get("automation") or ""): node
        for node in report.get("dependency_graph") or []
        if node.get("automation")
    }


def _record(by_alias, alias):
    records = by_alias.get(alias) or []
    return records[0] if len(records) == 1 else None


def _helper_phase_handoff(by_alias, node_map, a, b, target):
    rec_a = _record(by_alias, a)
    rec_b = _record(by_alias, b)
    if not rec_a or not rec_b:
        return None
    eff_a = rec_a.get("effective") or {}
    eff_b = rec_b.get("effective") or {}

    target_a = sem_v2._deterministic_intents(eff_a, target)
    target_b = sem_v2._deterministic_intents(eff_b, target)
    if len(target_a) != 1 or len(target_b) != 1 or target_a == target_b:
        return None

    node_a = node_map.get(a) or {}
    node_b = node_map.get(b) or {}
    directions = [
        (a, b, eff_a, eff_b, node_a, node_b, "a_to_b"),
        (b, a, eff_b, eff_a, node_b, node_a, "b_to_a"),
    ]
    for sender, receiver, eff_sender, eff_receiver, n_sender, n_receiver, direction in directions:
        sender_controls = {
            str(x) for x in n_sender.get("controls") or []
            if architecture_base._kind(str(x)) == "helper"
        }
        receiver_triggers = {str(x) for x in n_receiver.get("triggers_on") or []}
        candidates = sorted(sender_controls & receiver_triggers)
        if not candidates:
            continue
        profile = sem_v2._trigger_profile(eff_receiver)
        state_to = profile.get("state_to") or {}
        for helper in candidates:
            helper_intents = sem_v2._deterministic_intents(eff_sender, helper)
            trigger_states = set(str(x) for x in state_to.get(helper) or [])
            if len(helper_intents) != 1 or not trigger_states:
                continue
            helper_intent = next(iter(helper_intents))
            if not helper_intent.startswith("state:"):
                continue
            written_state = helper_intent.split(":", 1)[1]
            if written_state not in trigger_states:
                return {
                    "kind": "coordinated_protocol",
                    "reason": "helper_phase_handoff",
                    "evidence": {
                        "direction": direction,
                        "sender": sender,
                        "receiver": receiver,
                        "helper": helper,
                        "sender_helper_intent": helper_intent,
                        "receiver_trigger_states": sorted(trigger_states),
                        "target_intent_sender": sorted(target_a if sender == a else target_b),
                        "target_intent_receiver": sorted(target_b if receiver == b else target_a),
                    },
                }
    return None


def build_condition_semantics_v4(report):
    current = report.get("condition_semantics") or {}
    by_alias, parse_errors = sem_v1.effective_automation_map(report)
    nodes = _node_map(report)

    protocol_pairs = []
    remaining = []
    for pair in current.get("unproven_pairs") or []:
        target = str(pair.get("entity_id") or "")
        automations = [str(x) for x in pair.get("automations") or []]
        if architecture_base._kind(target) == "actuator" and len(automations) == 2:
            resolution = _helper_phase_handoff(by_alias, nodes, automations[0], automations[1], target)
            if resolution:
                protocol_pairs.append({
                    "entity_id": target,
                    "automations": automations,
                    "reason": resolution["reason"],
                    "evidence": resolution["evidence"],
                    "target_kind": "actuator",
                    "confidence": "high",
                })
                continue
        remaining.append(pair)

    protocol_keys = {
        (str(item.get("entity_id") or ""), frozenset(item.get("automations") or []))
        for item in protocol_pairs
    }
    contradictory = [
        item for item in current.get("contradictory_deterministic_pairs") or []
        if (str(item.get("entity_id") or ""), frozenset(item.get("automations") or [])) not in protocol_keys
    ]
    physical = [item for item in remaining if architecture_base._kind(str(item.get("entity_id") or "")) == "actuator"]
    helpers = [item for item in remaining if architecture_base._kind(str(item.get("entity_id") or "")) == "helper"]
    other = [item for item in remaining if architecture_base._kind(str(item.get("entity_id") or "")) not in {"actuator", "helper"}]

    existing_coordinated = list(current.get("coordinated_pairs") or [])
    coordinated = existing_coordinated + protocol_pairs
    existing_resolved = int(current.get("resolved_pair_count", 0) or 0)
    result = {
        **current,
        "model": CONDITION_MODEL,
        "protocol_coordinated_pair_count": len(protocol_pairs),
        "protocol_coordinated_pairs": protocol_pairs[:30],
        "coordinated_pair_count": len(coordinated),
        "coordinated_pairs": coordinated[:60],
        "resolved_pair_count": existing_resolved + len(protocol_pairs),
        "unproven_pair_count": len(remaining),
        "unproven_pairs": remaining[:60],
        "physical_unproven_pair_count": len(physical),
        "helper_unproven_pair_count": len(helpers),
        "other_unproven_pair_count": len(other),
        "contradictory_deterministic_pair_count": len(contradictory),
        "contradictory_deterministic_pairs": contradictory[:20],
        "parse_errors": (current.get("parse_errors") or parse_errors or [])[:12],
        "confidence": "high_for_resolved_deterministic_and_phase_handoff",
        "note": (
            "V4 reconnaît les handoffs de phase pilotés par helper quand une commande opposée "
            "ne peut être déclenchée qu'après une transition ultérieure du helper."
        ),
    }
    report["condition_semantics"] = result

    finding = next((x for x in report.get("findings") or [] if x.get("rule_id") == "HD-AUTO-003"), None)
    if finding:
        refined = []
        for raw in finding.get("examples") or []:
            example = dict(raw)
            entity = str(example.get("entity_id") or "")
            pairs = []
            for pair in example.get("unprotected_pairs") or []:
                key = (entity, frozenset(str(x) for x in pair))
                if key not in protocol_keys:
                    pairs.append(pair)
            example["unprotected_pairs"] = pairs
            example["unprotected_pair_count"] = len(pairs)
            if pairs:
                refined.append(example)
        finding["examples"] = refined
        finding["summary"] = (
            f"{len(physical)} paire(s) sur actionneur physique restent à vérifier, "
            f"{len(helpers)} paire(s) concernent seulement des helpers ; "
            f"{len(protocol_pairs)} handoff(s) de phase ont été reconnus."
        )
        finding["recommendation"] = (
            "Examiner les paires physiques restantes. Les handoffs de phase confirmés par helper "
            "sont séparés des conflits réellement non prouvés."
        )

    for explanation in report.get("diagnostic_explanations") or []:
        if str(explanation.get("source_id") or "") != "HD-AUTO-003":
            continue
        explanation["diagnosis"] = (
            f"{len(physical)} paire(s) physique(s) et {len(helpers)} paire(s) de helpers restent "
            f"non prouvées ; {len(protocol_pairs)} protocole(s) de handoff ont été reconnus."
        )
        evidence = [item for item in explanation.get("evidence") or [] if item.get("type") not in {"condition_semantics", "controller_protocol"}]
        evidence.append({
            "type": "condition_semantics",
            "label": "Coordination",
            "text": (
                f"{result.get('proven_exclusive_pair_count',0)} exclusives · "
                f"{result.get('coordinated_pair_count',0)} coordonnées · "
                f"{len(protocol_pairs)} handoff(s) · {len(remaining)} à vérifier"
            ),
        })
        if protocol_pairs:
            first = protocol_pairs[0]
            evidence.append({
                "type": "controller_protocol",
                "label": "Handoff détecté",
                "text": f"{first['evidence'].get('helper')} sépare les phases de {' ↔ '.join(first.get('automations') or [])}",
            })
        explanation["evidence"] = evidence[:12]
        explanation["why_now"] = (
            "La revue se concentre sur les couples physiques encore non expliqués ; les séquences "
            "de handoff démontrables sont déclassées."
        )

    arch = report.setdefault("architecture_analysis", {})
    arch.update({
        "condition_semantics_model": CONDITION_MODEL,
        "protocol_coordinated_pair_count": len(protocol_pairs),
        "physical_unproven_controller_pair_count": len(physical),
        "helper_unproven_controller_pair_count": len(helpers),
        "contradictory_deterministic_pair_count": len(contradictory),
    })
    return result
