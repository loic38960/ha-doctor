"""HA Doctor 0.8.2 controller-semantics and flow-confidence calibration.

The 0.8.1 engine only proves simple mandatory state guards. This layer keeps
that conservative proof model and adds a few high-confidence ways to resolve
controller pairs without executing Jinja:
- startup-only reconciliation writers;
- fixed time triggers that cannot occur together;
- state triggers with disjoint ``to`` values on the same entity;
- identical deterministic command intent on the shared target.

Ambiguous templates, OR/NOT conditions and dynamic command values remain
unproven.
"""

from collections import defaultdict

import semantics_v081 as base

VERSION = "0.8.2"
LOW_CONFIDENCE_WARNING_RATIO = 0.25


def build_flow_confidence_v2(report):
    """Extend the 0.8.1 confidence report with an explicit quality verdict."""
    result = report.get("flow_confidence") or base.build_flow_confidence(report)
    bands = result.get("dynamic_confidence_bands") or {}
    dynamic_total = sum(int(bands.get(key, 0) or 0) for key in ("high", "inferred", "heuristic"))
    low = int(result.get("low_confidence_dynamic_edges", 0) or 0)
    unresolved = int(result.get("unresolved_dynamic_targets", 0) or 0)
    low_ratio = (low / dynamic_total) if dynamic_total else 0.0

    if unresolved:
        quality = "fail"
    elif int(bands.get("heuristic", 0) or 0) > 0 or low_ratio >= LOW_CONFIDENCE_WARNING_RATIO:
        quality = "warning"
    else:
        quality = "pass"

    result.update({
        "model": "flow_confidence_v2",
        "dynamic_edge_count": dynamic_total,
        "low_confidence_ratio": round(low_ratio, 3),
        "low_confidence_warning_ratio": LOW_CONFIDENCE_WARNING_RATIO,
        "quality_status": quality,
        "interpretation": (
            "Une cible résolue n'est pas automatiquement certaine. Le gate passe seulement "
            "si aucune cible n'est non résolue et si la part de cibles inférées/heuristiques "
            "reste limitée."
        ),
    })
    report["flow_confidence"] = result
    report.setdefault("dependency_graph_meta", {}).update({
        "confidence_model": result["model"],
        "low_confidence_ratio": result["low_confidence_ratio"],
    })
    return result


def _trigger_list(effective):
    raw = effective.get("triggers", effective.get("trigger", [])) if isinstance(effective, dict) else []
    if raw is None:
        return []
    return raw if isinstance(raw, list) else [raw]


def _trigger_profile(effective):
    triggers = [item for item in _trigger_list(effective) if isinstance(item, dict)]
    platforms = [str(item.get("platform") or item.get("trigger") or "").lower() for item in triggers]

    startup = [
        item for item, platform in zip(triggers, platforms)
        if platform == "homeassistant" and str(item.get("event") or "").lower() == "start"
    ]
    fixed_times = set()
    only_fixed_time = bool(triggers)
    state_to = defaultdict(set)
    only_state_to = bool(triggers)

    for item, platform in zip(triggers, platforms):
        if platform == "time" and isinstance(item.get("at"), (str, int, float)):
            fixed_times.add(str(item.get("at")))
        else:
            only_fixed_time = False

        if platform == "state":
            entities = base.flow._entity_ids(item.get("entity_id"))
            to_value = item.get("to")
            if entities and isinstance(to_value, (str, int, float, bool)):
                for entity_id in entities:
                    state_to[str(entity_id)].add(str(to_value))
            else:
                only_state_to = False
        else:
            only_state_to = False

    return {
        "trigger_count": len(triggers),
        "startup_only": bool(triggers) and len(startup) == len(triggers),
        "only_fixed_time": only_fixed_time,
        "fixed_times": fixed_times,
        "only_state_to": only_state_to,
        "state_to": dict(state_to),
    }


def _entity_ids(value):
    try:
        return set(base.flow._entity_ids(value))
    except Exception:
        return set()


def _fixed_scalar(value):
    if not isinstance(value, (str, int, float, bool)):
        return None
    text = str(value)
    if "{{" in text or "{%" in text or "!input" in text:
        return None
    return text


def _deterministic_intents(effective, target_entity):
    """Return only command intents that are safe to compare statically."""
    intents = set()

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return

        service = value.get("service")
        if not isinstance(service, str):
            action_value = value.get("action")
            service = action_value if isinstance(action_value, str) and "." in action_value else None

        if service:
            target = value.get("target") or {}
            data = value.get("data") or {}
            ids = set()
            if isinstance(target, dict):
                ids |= _entity_ids(target.get("entity_id"))
            if isinstance(data, dict):
                ids |= _entity_ids(data.get("entity_id"))

            if target_entity in ids:
                normalized = service.lower()
                if normalized.endswith(".turn_on"):
                    intents.add("state:on")
                elif normalized.endswith(".turn_off"):
                    intents.add("state:off")
                elif normalized.endswith(".open_cover"):
                    intents.add("cover:open")
                elif normalized.endswith(".close_cover"):
                    intents.add("cover:closed")
                elif normalized in {"select.select_option", "input_select.select_option"}:
                    option = _fixed_scalar(data.get("option") if isinstance(data, dict) else None)
                    if option is not None:
                        intents.add(f"option:{option}")
                elif normalized == "climate.set_hvac_mode":
                    mode = _fixed_scalar(data.get("hvac_mode") if isinstance(data, dict) else None)
                    if mode is not None:
                        intents.add(f"hvac_mode:{mode}")
                elif normalized in {"number.set_value", "input_number.set_value"}:
                    number = _fixed_scalar(data.get("value") if isinstance(data, dict) else None)
                    if number is not None:
                        intents.add(f"value:{number}")

        for child in value.values():
            if isinstance(child, (dict, list)):
                walk(child)

    walk(effective)
    return intents


def resolve_controller_pair(record_a, record_b, target_entity):
    """Return a conservative resolution for one controller pair, or None."""
    effective_a = record_a.get("effective") or {}
    effective_b = record_b.get("effective") or {}
    profile_a = _trigger_profile(effective_a)
    profile_b = _trigger_profile(effective_b)

    # Startup-only writers are treated as reconciliation writers, not runtime
    # competitors. They run only during HA startup and repair/synchronise state.
    if profile_a["startup_only"] != profile_b["startup_only"]:
        startup_alias = "a" if profile_a["startup_only"] else "b"
        return {
            "kind": "coordinated",
            "reason": "startup_reconciliation_writer",
            "evidence": {"startup_only_side": startup_alias},
        }

    # Two automations that only run at different fixed clock times cannot race
    # under normal scheduler semantics.
    if profile_a["only_fixed_time"] and profile_b["only_fixed_time"]:
        if profile_a["fixed_times"] and profile_b["fixed_times"] and profile_a["fixed_times"].isdisjoint(profile_b["fixed_times"]):
            return {
                "kind": "exclusive",
                "reason": "disjoint_fixed_time_triggers",
                "evidence": {
                    "times_a": sorted(profile_a["fixed_times"]),
                    "times_b": sorted(profile_b["fixed_times"]),
                },
            }

    # State transitions to different states on the same entity are exclusive
    # when those are the only triggers of each automation.
    if profile_a["only_state_to"] and profile_b["only_state_to"]:
        for entity_id in sorted(set(profile_a["state_to"]) & set(profile_b["state_to"])):
            states_a = set(profile_a["state_to"].get(entity_id) or ())
            states_b = set(profile_b["state_to"].get(entity_id) or ())
            if states_a and states_b and states_a.isdisjoint(states_b):
                return {
                    "kind": "exclusive",
                    "reason": "disjoint_state_transition_triggers",
                    "evidence": {
                        "entity_id": entity_id,
                        "to_a": sorted(states_a),
                        "to_b": sorted(states_b),
                    },
                }

    # If both automations can only issue the exact same deterministic command
    # on the shared target, this is redundant coordination rather than a
    # contradictory controller pair. Dynamic payloads are deliberately ignored.
    intents_a = _deterministic_intents(effective_a, target_entity)
    intents_b = _deterministic_intents(effective_b, target_entity)
    if len(intents_a) == 1 and intents_a == intents_b:
        return {
            "kind": "coordinated",
            "reason": "same_deterministic_command",
            "evidence": {"intent": next(iter(intents_a))},
        }

    return None


def build_condition_semantics_v2(report):
    """Refine the remaining 0.8.1 controller pairs with trigger semantics."""
    current = report.get("condition_semantics") or {}
    by_alias, parse_errors = base.effective_automation_map(report)
    finding = next(
        (item for item in report.get("findings") or [] if item.get("rule_id") == "HD-AUTO-003"),
        None,
    )

    existing_proven = list(current.get("proven_exclusive_pairs") or [])
    exclusive_v2 = []
    coordinated = []
    unresolved = []
    refined_examples = []

    if finding:
        for raw_example in finding.get("examples") or []:
            example = dict(raw_example)
            target_entity = str(example.get("entity_id") or "")
            remaining = []
            local_resolved = []
            for pair in example.get("unprotected_pairs") or []:
                if not isinstance(pair, list) or len(pair) != 2:
                    remaining.append(pair)
                    continue
                a, b = str(pair[0]), str(pair[1])
                records_a = by_alias.get(a) or []
                records_b = by_alias.get(b) or []
                resolution = None
                if len(records_a) == 1 and len(records_b) == 1:
                    resolution = resolve_controller_pair(records_a[0], records_b[0], target_entity)

                if not resolution:
                    remaining.append(pair)
                    unresolved.append({"entity_id": target_entity, "automations": [a, b]})
                    continue

                item = {
                    "entity_id": target_entity,
                    "automations": [a, b],
                    "reason": resolution["reason"],
                    "evidence": resolution.get("evidence") or {},
                }
                local_resolved.append(item)
                if resolution["kind"] == "exclusive":
                    exclusive_v2.append(item)
                else:
                    coordinated.append(item)

            example["unprotected_pairs"] = remaining
            example["unprotected_pair_count"] = len(remaining)
            example["v2_resolved_pair_count"] = len(local_resolved)
            if local_resolved:
                example["v2_resolved_pairs"] = local_resolved
            if remaining:
                refined_examples.append(example)

        finding["examples"] = refined_examples
        total_resolved = len(existing_proven) + len(exclusive_v2) + len(coordinated)
        finding["summary"] = (
            f"{len(refined_examples)} entité(s) gardent au moins une paire de contrôleurs "
            f"sans coordination démontrée. {total_resolved} paire(s) ont été écartées "
            "par conditions, déclencheurs ou commandes déterministes."
        )
        finding["recommendation"] = (
            "Examiner uniquement les paires restantes. Les écritures de restauration au "
            "démarrage, horaires incompatibles et commandes identiques sont séparées des "
            "vrais conflits potentiels."
        )

    proven = existing_proven + exclusive_v2
    result = {
        **current,
        "model": "condition_semantics_v2",
        "proven_exclusive_pair_count": len(proven),
        "coordinated_pair_count": len(coordinated),
        "resolved_pair_count": len(proven) + len(coordinated),
        "unproven_pair_count": len(unresolved),
        "proven_exclusive_pairs": proven[:40],
        "coordinated_pairs": coordinated[:40],
        "unproven_pairs": unresolved[:40],
        "parse_errors": (current.get("parse_errors") or parse_errors or [])[:12],
        "confidence": "high_for_resolved_pairs_only",
        "note": (
            "V2 ajoute horaires fixes, transitions d'état, writers de resynchronisation au "
            "démarrage et commandes déterministes. Les templates ambigus restent à vérifier."
        ),
    }
    report["condition_semantics"] = result

    architecture = report.setdefault("architecture_analysis", {})
    architecture.update({
        "condition_semantics_model": result["model"],
        "proven_exclusive_controller_pair_count": result["proven_exclusive_pair_count"],
        "coordinated_controller_pair_count": result["coordinated_pair_count"],
        "unproven_controller_pair_count": result["unproven_pair_count"],
    })

    for explanation in report.get("diagnostic_explanations") or []:
        if str(explanation.get("source_id") or "") != "HD-AUTO-003":
            continue
        explanation["diagnosis"] = (
            f"HA Doctor a résolu {result['resolved_pair_count']} paire(s) de contrôleurs "
            f"sans conflit démontré ; {result['unproven_pair_count']} paire(s) restent à vérifier."
        )
        evidence = [
            item for item in (explanation.get("evidence") or [])
            if item.get("type") != "condition_semantics"
        ]
        evidence.append({
            "type": "condition_semantics",
            "label": "Paires résolues",
            "text": (
                f"{result['proven_exclusive_pair_count']} exclusives · "
                f"{result['coordinated_pair_count']} coordonnées · "
                f"{result['unproven_pair_count']} à vérifier"
            ),
        })
        explanation["evidence"] = evidence[:12]

    return result
