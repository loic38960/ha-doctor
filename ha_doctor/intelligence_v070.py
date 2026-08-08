"""HA Doctor 0.7 intelligence engine.

This layer turns the deterministic 0.5 diagnostic output into a correlated,
dependency-aware, temporal and product-oriented report without changing Home
Assistant. It intentionally stores no raw states and performs no automatic fix.
"""

import re
from collections import Counter, defaultdict

from temporal_v060 import HISTORY_LIMIT, load_history, save_history

VERSION = "0.7.0"
REPORT_SCHEMA_VERSION = "ha-doctor-report/0.7"

PRIORITY_ORDER = {"action_now": 0, "verify": 1, "optimize": 2, "info": 3}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

ENTITY_RE = re.compile(
    r"\b(?:alarm_control_panel|automation|binary_sensor|button|calendar|camera|climate|counter|cover|datetime|device_tracker|event|group|image|input_boolean|input_datetime|input_number|input_select|input_text|lawn_mower|light|lock|media_player|notify|number|person|remote|scene|script|select|sensor|siren|stt|sun|switch|text|time|timer|todo|tts|update|vacuum|valve|water_heater|weather|zone)\.[a-zA-Z0-9_]+\b"
)

# Objects that are Home Assistant service/action names, not entity object_ids.
SERVICE_OBJECTS = {
    "turn_on", "turn_off", "toggle", "reload", "restart", "stop", "start",
    "set_value", "set_datetime", "set_date", "set_time", "select_option",
    "select_first", "select_last", "select_next", "select_previous",
    "set_temperature", "set_hvac_mode", "set_fan_mode", "set_preset_mode",
    "set_swing_mode", "set_humidity", "open_cover", "close_cover",
    "toggle_cover", "stop_cover", "set_cover_position", "set_cover_tilt_position",
    "open_cover_tilt", "close_cover_tilt", "stop_cover_tilt", "lock", "unlock",
    "open", "close", "set_position", "set_tilt_position", "alarm_arm_away",
    "alarm_arm_home", "alarm_arm_night", "alarm_arm_vacation", "alarm_disarm",
    "alarm_trigger", "reset", "increment", "decrement", "pause", "cancel",
    "finish", "play_media", "media_play", "media_pause", "media_stop",
    "media_next_track", "media_previous_track", "volume_set", "volume_up",
    "volume_down", "volume_mute", "join", "unjoin", "clear_playlist",
    "shuffle_set", "repeat_set", "seek", "snapshot", "record", "enable_motion_detection",
    "disable_motion_detection", "press", "send_command", "learn_command",
    "delete_command", "publish", "get_items", "add_item", "update_item",
    "remove_item", "remove_completed_items", "speak", "say", "announce",
    "set_percentage", "set_direction", "set_speed", "return_to_base", "locate",
    "clean_spot", "send_to_target", "set_fan_speed", "start_pause", "dock",
    "set_option", "set_level", "set_color", "set_color_temp", "set_brightness",
}

ACTUATOR_DOMAINS = {
    "alarm_control_panel", "climate", "cover", "fan", "lawn_mower", "light",
    "lock", "media_player", "remote", "siren", "switch", "vacuum", "valve",
    "water_heater",
}
HELPER_DOMAINS = {
    "counter", "group", "input_boolean", "input_datetime", "input_number",
    "input_select", "input_text", "timer",
}
SENSOR_DOMAINS = {
    "binary_sensor", "calendar", "camera", "device_tracker", "event", "image",
    "person", "sensor", "sun", "weather", "zone",
}
OPTIONAL_DOMAINS = {"button", "number", "select", "text", "time", "update"}

NOISE_RULES_WHEN_ROOT_CAUSES_EXIST = {"HD-ENT-001", "HD-ENT-003"}


def _domain(entity_id):
    return str(entity_id or "").split(".", 1)[0] if "." in str(entity_id or "") else ""


def _kind(entity_id):
    domain = _domain(entity_id)
    if domain in ACTUATOR_DOMAINS:
        return "actuator"
    if domain in HELPER_DOMAINS:
        return "helper"
    if domain in SENSOR_DOMAINS:
        return "sensor"
    if domain in OPTIONAL_DOMAINS:
        return "optional"
    return "other"


def _is_entity_ref(value, allowed_domains):
    value = str(value or "")
    if "." not in value:
        return False
    domain, obj = value.split(".", 1)
    if domain not in allowed_domains or not obj:
        return False
    if obj in SERVICE_OBJECTS:
        return False
    return bool(re.fullmatch(r"[a-zA-Z0-9_]+", obj))


def clean_dependency_graph(report):
    """Remove service calls from references and build a clean entity graph."""
    inventory = report.get("inventory") or {}
    allowed_domains = set((inventory.get("domains") or {}).keys())
    graph = []
    before_refs = 0
    removed_services = 0
    entity_edges = 0
    trigger_edges = 0
    control_edges = 0

    for raw in report.get("dependency_graph") or []:
        node = dict(raw)
        raw_refs = [str(x) for x in (raw.get("references") or []) if isinstance(x, str)]
        raw_triggers = [str(x) for x in (raw.get("triggers_on") or []) if isinstance(x, str)]
        raw_controls = [str(x) for x in (raw.get("controls") or []) if isinstance(x, str)]
        before_refs += len(raw_refs)

        refs = sorted(set(x for x in raw_refs if _is_entity_ref(x, allowed_domains)))
        triggers = sorted(set(x for x in raw_triggers if _is_entity_ref(x, allowed_domains)))
        controls = sorted(set(x for x in raw_controls if _is_entity_ref(x, allowed_domains)))
        removed_services += max(0, len(raw_refs) - len(refs))

        reads = sorted(set(refs) - set(triggers) - set(controls))
        all_entities = sorted(set(refs) | set(triggers) | set(controls))
        node["references"] = refs
        node["triggers_on"] = triggers
        node["controls"] = controls
        node["reads"] = reads
        node["entities"] = all_entities
        node["service_references_removed"] = max(0, len(raw_refs) - len(refs))
        graph.append(node)

        entity_edges += len(all_entities)
        trigger_edges += len(triggers)
        control_edges += len(controls)

    report["dependency_graph"] = graph
    report["dependency_graph_meta"] = {
        "model": "entity_graph_v2",
        "automation_nodes": len(graph),
        "references_before_cleanup": before_refs,
        "service_references_removed": removed_services,
        "entity_edges": entity_edges,
        "trigger_edges": trigger_edges,
        "control_edges": control_edges,
        "service_calls_are_entities": False,
    }
    return graph


def build_architecture(report):
    """Build entity hot-spots and automation topology from the clean graph."""
    graph = report.get("dependency_graph") or []
    by_entity = defaultdict(lambda: {
        "triggers": set(), "controls": set(), "reads": set(), "references": set()
    })
    source_counts = Counter()
    closed_loops = []
    automation_profiles = []

    for node in graph:
        name = str(node.get("automation") or "Automatisation")
        source = str(node.get("source") or "")
        if source:
            source_counts[source] += 1
        triggers = set(node.get("triggers_on") or [])
        controls = set(node.get("controls") or [])
        reads = set(node.get("reads") or [])
        refs = set(node.get("references") or [])
        for ent in triggers:
            by_entity[ent]["triggers"].add(name)
        for ent in controls:
            by_entity[ent]["controls"].add(name)
        for ent in reads:
            by_entity[ent]["reads"].add(name)
        for ent in refs:
            by_entity[ent]["references"].add(name)

        self_entities = sorted(triggers & controls)
        if self_entities:
            closed_loops.append({
                "automation": name,
                "source": source,
                "entities": self_entities[:8],
                "count": len(self_entities),
            })

        actuator_controls = sorted(x for x in controls if _kind(x) == "actuator")
        helper_controls = sorted(x for x in controls if _kind(x) == "helper")
        risk = (
            len(actuator_controls) * 4.0
            + len(triggers) * 1.5
            + len(reads) * 0.5
            + (3.0 if self_entities else 0.0)
            + max(0, len(controls) - 1) * 0.6
        )
        automation_profiles.append({
            "automation": name,
            "source": source,
            "trigger_count": len(triggers),
            "control_count": len(controls),
            "actuator_control_count": len(actuator_controls),
            "helper_control_count": len(helper_controls),
            "read_count": len(reads),
            "self_feedback": bool(self_entities),
            "risk_index": round(risk, 1),
            "actuators": actuator_controls[:6],
        })

    hotspots = []
    for entity_id, sets in by_entity.items():
        kind = _kind(entity_id)
        trigger_count = len(sets["triggers"])
        control_count = len(sets["controls"])
        read_count = len(sets["reads"])
        reference_count = len(sets["references"])
        kind_weight = {"actuator": 1.35, "sensor": 1.0, "helper": 0.38, "optional": 0.45}.get(kind, 0.7)
        raw_score = (
            trigger_count * 2.4
            + control_count * (5.0 if kind == "actuator" else 2.0)
            + read_count * 0.9
            + reference_count * 0.35
        ) * kind_weight
        hotspots.append({
            "entity_id": entity_id,
            "kind": kind,
            "triggered_automations": trigger_count,
            "controlling_automations": control_count,
            "reading_automations": read_count,
            "referencing_automations": reference_count,
            "criticality": min(100, int(round(raw_score * 4.0))),
            "controllers": sorted(sets["controls"])[:8],
            "triggers": sorted(sets["triggers"])[:8],
        })

    hotspots.sort(key=lambda x: (-x["criticality"], x["entity_id"]))
    automation_profiles.sort(key=lambda x: (-x["risk_index"], x["automation"]))

    shared_actuators = [x for x in hotspots if x["kind"] == "actuator" and x["controlling_automations"] > 1]
    helper_hubs = [x for x in hotspots if x["kind"] == "helper" and x["controlling_automations"] > 1]
    trigger_hubs = [x for x in hotspots if x["triggered_automations"] >= 3]

    edges = int((report.get("dependency_graph_meta") or {}).get("entity_edges", 0) or 0)
    states = int((report.get("inventory") or {}).get("states", 0) or 0)
    automations = len(graph)
    integrations = int((((report.get("registry_analysis") or {}).get("integration_health") or {}).get("total", 0) or 0))
    complexity = min(100, int(round(states / 90.0 + automations * 0.34 + integrations * 0.24 + edges * 0.025)))
    if complexity >= 75:
        complexity_label = "Très complexe"
    elif complexity >= 55:
        complexity_label = "Avancée"
    elif complexity >= 35:
        complexity_label = "Intermédiaire"
    else:
        complexity_label = "Simple"

    architecture = {
        "model": "architecture_v1",
        "complexity_score": complexity,
        "complexity_label": complexity_label,
        "automation_count": automations,
        "entity_dependency_count": len(by_entity),
        "entity_edge_count": edges,
        "shared_actuator_count": len(shared_actuators),
        "helper_hub_count": len(helper_hubs),
        "trigger_hub_count": len(trigger_hubs),
        "closed_loop_count": len(closed_loops),
        "top_hotspots": hotspots[:20],
        "shared_actuators": shared_actuators[:15],
        "helper_hubs": helper_hubs[:15],
        "trigger_hubs": trigger_hubs[:15],
        "closed_loops": closed_loops[:15],
        "automation_risk_profiles": automation_profiles[:20],
        "top_sources": [
            {"source": src, "automation_count": count}
            for src, count in source_counts.most_common(15)
        ],
        "note": "La complexité décrit l'architecture ; elle ne réduit pas directement l'indice de santé.",
    }
    report["architecture_analysis"] = architecture
    return architecture


def _registry_examples(report, explanation):
    registry = report.get("registry_analysis") or {}
    source_type = str(explanation.get("source_type") or "")
    source_id = str(explanation.get("source_id") or "")
    examples = []
    if source_type == "registry_integration":
        for item in ((registry.get("integration_health") or {}).get("groups") or []):
            if str(item.get("integration") or "") == source_id:
                examples.extend(item.get("examples") or [])
                break
    elif source_type == "registry_device":
        for item in ((registry.get("device_health") or {}).get("groups") or []):
            if str(item.get("name") or "") == source_id:
                examples.extend(item.get("examples") or [])
                break
    elif source_type == "registry_cluster":
        for item in ((registry.get("device_health") or {}).get("groups") or []):
            if source_id in {str(x) for x in (item.get("platforms") or [])} and item.get("status") == "offline":
                examples.extend(item.get("examples") or [])
    return [str(x) for x in examples if isinstance(x, str)]


def _explanation_entities(report, explanation):
    values = []
    for evidence in explanation.get("evidence") or []:
        text = str(evidence.get("text") or "") if isinstance(evidence, dict) else str(evidence)
        values.extend(ENTITY_RE.findall(text))
    values.extend(_registry_examples(report, explanation))
    return sorted(set(x for x in values if ENTITY_RE.fullmatch(x)))


def add_dependency_impact(report, explanations):
    """Compute blast radius while heavily discounting helper-only fan-out."""
    graph = report.get("dependency_graph") or []
    for item in explanations:
        entities = set(_explanation_entities(report, item))
        impacted = set()
        critical_automations = set()
        helper_only = set()
        trigger_hits = 0
        control_hits = 0
        weighted = 0.0
        entity_impacts = []

        for ent in entities:
            kind = _kind(ent)
            ent_impacted = set()
            ent_triggers = 0
            ent_controls = 0
            ent_reads = 0
            for node in graph:
                name = str(node.get("automation") or "Automatisation")
                triggers = set(node.get("triggers_on") or [])
                controls = set(node.get("controls") or [])
                reads = set(node.get("reads") or [])
                refs = set(node.get("references") or [])
                if ent in triggers | controls | reads | refs:
                    impacted.add(name)
                    ent_impacted.add(name)
                    if kind in {"actuator", "sensor"}:
                        critical_automations.add(name)
                    elif kind == "helper":
                        helper_only.add(name)
                if ent in triggers:
                    trigger_hits += 1
                    ent_triggers += 1
                if ent in controls:
                    control_hits += 1
                    ent_controls += 1
                if ent in reads:
                    ent_reads += 1

            kind_weight = {"actuator": 1.25, "sensor": 1.0, "helper": 0.28, "optional": 0.35}.get(kind, 0.6)
            contribution = kind_weight * (ent_triggers * 2.0 + ent_controls * 2.8 + ent_reads * 0.7 + len(ent_impacted) * 0.35)
            weighted += contribution
            if ent_impacted:
                entity_impacts.append({
                    "entity_id": ent,
                    "kind": kind,
                    "automation_count": len(ent_impacted),
                    "trigger_hits": ent_triggers,
                    "control_hits": ent_controls,
                    "weight": round(contribution, 2),
                })

        entity_impacts.sort(key=lambda x: (-x["weight"], x["entity_id"]))
        if weighted >= 12 or len(critical_automations) >= 6:
            level, multiplier = "high", 1.15
        elif weighted >= 4 or len(critical_automations) >= 2:
            level, multiplier = "medium", 1.07
        else:
            level, multiplier = "low", 1.0

        item["dependency_impact"] = {
            "level": level,
            "impacted_automation_count": len(impacted),
            "critical_automation_count": len(critical_automations),
            "helper_only_automation_count": len(helper_only - critical_automations),
            "impacted_automations": sorted(impacted)[:10],
            "critical_automations": sorted(critical_automations)[:10],
            "trigger_dependency_count": trigger_hits,
            "control_dependency_count": control_hits,
            "weighted_impact_score": round(weighted, 2),
            "score_multiplier": multiplier,
            "top_entities": entity_impacts[:6],
            "helper_fanout_discounted": True,
        }
    return explanations


def add_temporal_context(explanations, history, generated_at):
    previous = history[-1] if history else None
    prior_ids = [set(x.get("active_ids") or []) for x in history]
    previous_ids = set(previous.get("active_ids") or []) if previous else set()

    for item in explanations:
        item_id = str(item.get("id") or "")
        occurrences = sum(1 for ids in prior_ids if item_id in ids) + 1
        consecutive = 1
        for ids in reversed(prior_ids):
            if item_id in ids:
                consecutive += 1
            else:
                break

        first_seen = None
        for snap in history:
            if item_id in set(snap.get("active_ids") or []):
                first_seen = snap.get("generated_at")
                break
        if first_seen is None:
            first_seen = generated_at

        if not previous:
            status = "baseline"
        elif item_id not in previous_ids:
            status = "new" if occurrences == 1 else "recurrent"
        elif consecutive >= 2:
            status = "persistent"
        else:
            status = "recurrent"

        source_type = str(item.get("source_type") or "")
        if source_type.startswith("registry_"):
            if status in {"baseline", "new"}:
                factor = 0.68
            elif consecutive == 2:
                factor = 0.86
            elif consecutive == 3:
                factor = 0.95
            else:
                factor = 1.0
        else:
            factor = 1.0

        item["temporal"] = {
            "status": status,
            "occurrences": occurrences,
            "consecutive_scans": consecutive,
            "first_seen": first_seen,
            "persistence_factor": factor,
        }
    return explanations


def _sort_key(item):
    temporal = item.get("temporal") or {}
    return (
        PRIORITY_ORDER.get(item.get("priority"), 9),
        SEVERITY_ORDER.get(item.get("severity"), 9),
        -float(item.get("confidence_score", 0) or 0),
        -int(temporal.get("consecutive_scans", 0) or 0),
        item.get("title", ""),
    )


def _plan_explanations(report, explanations):
    root_causes = [x for x in explanations if str(x.get("source_type") or "").startswith("registry_")]
    probable_orphans = int((((report.get("registry_analysis") or {}).get("orphan_analysis") or {}).get("probable_orphan_count", 0) or 0))
    result = []
    suppressed = []
    seen = set()

    for item in sorted(explanations, key=_sort_key):
        item_id = str(item.get("id") or "")
        if not item_id or item_id in seen:
            if item_id:
                suppressed.append({"id": item_id, "reason": "duplicate_diagnostic"})
            continue
        seen.add(item_id)
        if item.get("priority") not in {"action_now", "verify", "optimize"}:
            continue
        rule_id = item.get("rule_id")
        if root_causes and rule_id in NOISE_RULES_WHEN_ROOT_CAUSES_EXIST:
            suppressed.append({"id": item_id, "reason": "explained_by_root_causes"})
            continue
        if rule_id == "HD-REG-002" and probable_orphans == 0 and item.get("confidence") == "low":
            suppressed.append({"id": item_id, "reason": "low_confidence_registry_review"})
            continue
        result.append(item)
    return result, suppressed


def _penalty(item):
    table = {
        "action_now": {"critical": 7.0, "high": 5.0, "medium": 3.2, "low": 1.5, "info": 0.0},
        "verify": {"critical": 3.0, "high": 2.1, "medium": 1.45, "low": 0.65, "info": 0.0},
        "optimize": {"critical": 1.0, "high": 0.75, "medium": 0.55, "low": 0.34, "info": 0.0},
    }
    base = table.get(item.get("priority"), {}).get(item.get("severity"), 0.0)
    confidence = max(0.45, min(1.0, float(item.get("confidence_score", 0.6) or 0.6)))
    dep = float(((item.get("dependency_impact") or {}).get("score_multiplier", 1.0) or 1.0))
    temporal = float(((item.get("temporal") or {}).get("persistence_factor", 1.0) or 1.0))
    return base * confidence * dep * temporal


def build_score_v4(report, plan_items, history):
    domain_penalties = defaultdict(float)
    breakdown = []
    for item in plan_items:
        penalty = _penalty(item)
        if penalty <= 0:
            continue
        domain = str(item.get("domain") or "configuration")
        domain_penalties[domain] += penalty
        breakdown.append({
            "id": item.get("id"),
            "title": item.get("title"),
            "domain": domain,
            "penalty": round(penalty, 2),
            "confidence": item.get("confidence_score"),
            "temporal_status": (item.get("temporal") or {}).get("status"),
            "dependency_impact": (item.get("dependency_impact") or {}).get("level"),
        })

    # Category caps prevent a single integration with many entities from being
    # counted repeatedly while keeping genuinely different root causes visible.
    caps = {
        "system": 8.0,
        "entities": 13.0,
        "automations": 16.0,
        "configuration": 13.0,
        "security": 15.0,
        "performance": 8.0,
    }
    capped = {domain: min(value, caps.get(domain, 12.0)) for domain, value in domain_penalties.items()}
    total_penalty = min(55.0, sum(capped.values()))
    global_score = int(round(max(45.0, 100.0 - total_penalty)))

    domains = {}
    for domain in ["system", "entities", "automations", "configuration", "security", "performance"]:
        penalty = capped.get(domain, 0.0)
        domains[domain] = int(round(max(45.0, 100.0 - penalty * 3.0)))

    previous_score = None
    if history:
        previous = history[-1]
        previous_score = previous.get("health_score_v4")
        if previous_score is None:
            previous_score = previous.get("health_score_v3")

    breakdown.sort(key=lambda x: -x["penalty"])
    return {
        "global": global_score,
        "domains": domains,
        "penalty_total": round(total_penalty, 2),
        "domain_penalties": {k: round(v, 2) for k, v in capped.items()},
        "breakdown": breakdown,
        "previous_score": previous_score,
    }


def _action_item(explanation):
    checks = explanation.get("checks") or []
    temporal = explanation.get("temporal") or {}
    dep = explanation.get("dependency_impact") or {}
    persistence = int(temporal.get("consecutive_scans", 0) or 0)
    impact_level = str(dep.get("level") or "low")
    if explanation.get("priority") == "action_now":
        why_now = "Priorité élevée dans le moteur de règles."
    elif persistence >= 3:
        why_now = f"Diagnostic présent sur {persistence} scans consécutifs."
    elif impact_level == "high":
        why_now = "Impact élevé sur le graphe d'automatisations."
    elif explanation.get("confidence") == "high":
        why_now = "Confiance élevée du diagnostic."
    else:
        why_now = "Point retenu après corrélation et suppression du bruit."

    return {
        "id": explanation.get("id"),
        "title": explanation.get("title"),
        "priority": explanation.get("priority"),
        "priority_label": explanation.get("priority_label"),
        "severity": explanation.get("severity"),
        "domain": explanation.get("domain"),
        "confidence": explanation.get("confidence"),
        "confidence_label": explanation.get("confidence_label"),
        "confidence_score": explanation.get("confidence_score"),
        "diagnosis": explanation.get("diagnosis"),
        "impact": explanation.get("impact"),
        "why_now": why_now,
        "first_check": checks[0] if checks else None,
        "source_type": explanation.get("source_type"),
        "source_id": explanation.get("source_id"),
        "temporal": temporal,
        "dependency_impact": dep,
    }


def _health_label(score):
    if score is None:
        return "Inconnu"
    if score >= 92:
        return "Excellent"
    if score >= 82:
        return "Bon"
    if score >= 70:
        return "À surveiller"
    if score >= 55:
        return "À corriger"
    return "Critique"


def _finding_by_rule(report):
    return {str(x.get("rule_id")): x for x in (report.get("findings") or []) if x.get("rule_id")}


def build_maintenance_debt(report):
    findings = _finding_by_rule(report)
    missing_refs = len((findings.get("HD-CFG-001") or {}).get("examples") or [])
    archive_secret_hits = len((findings.get("HD-SEC-003") or {}).get("examples") or [])
    local_review = int((((report.get("registry_analysis") or {}).get("orphan_analysis") or {}).get("review_candidate_count", 0) or 0))
    probable_orphans = int((((report.get("registry_analysis") or {}).get("orphan_analysis") or {}).get("probable_orphan_count", 0) or 0))
    active_yaml = int((report.get("inventory") or {}).get("automations_detected", 0) or 0)
    active_entities = int(((report.get("inventory") or {}).get("domains") or {}).get("automation", 0) or 0)
    coverage = 1.0 if active_entities <= 0 else min(1.0, active_yaml / active_entities)
    coverage_gap = max(0, active_entities - active_yaml)
    score = min(100, int(round(missing_refs * 4 + probable_orphans * 7 + local_review * 0.7 + archive_secret_hits * 0.7 + coverage_gap * 1.2)))
    if score >= 55:
        label = "Élevée"
    elif score >= 25:
        label = "Modérée"
    else:
        label = "Faible"
    return {
        "model": "maintenance_debt_v1",
        "score": score,
        "label": label,
        "missing_reference_count": missing_refs,
        "probable_orphan_count": probable_orphans,
        "local_review_candidate_count": local_review,
        "archived_secret_hint_count": archive_secret_hits,
        "automation_coverage_ratio": round(coverage, 3),
        "automation_coverage_gap": coverage_gap,
        "note": "La dette de maintenance est informative et ne remplace pas l'indice de santé.",
    }


def build_quality_gates(report):
    diagnostics = report.get("diagnostics") or {}
    registry = report.get("registry_analysis") or {}
    privacy = report.get("privacy") or {}
    graph_meta = report.get("dependency_graph_meta") or {}
    plan = report.get("action_plan") or {}
    summary = report.get("diagnostic_summary") or {}

    gates = []

    def add(key, label, status, detail):
        gates.append({"key": key, "label": label, "status": status, "detail": detail})

    api_errors = len(diagnostics.get("api_errors") or [])
    yaml_errors = len(diagnostics.get("yaml_parse_errors") or [])
    unresolved = len(diagnostics.get("unresolved_blueprints") or [])
    add("api", "API Home Assistant", "pass" if api_errors == 0 else "fail", f"{api_errors} erreur(s) API")
    add("yaml", "Parsing YAML", "pass" if yaml_errors == 0 else "fail", f"{yaml_errors} erreur(s) YAML")
    add("blueprints", "Résolution blueprints", "pass" if unresolved == 0 else "warn", f"{unresolved} blueprint(s) non résolu(s)")
    add("registry", "Registres Home Assistant", "pass" if registry.get("available") else "warn", "Disponible" if registry.get("available") else "Non disponible")
    privacy_ok = privacy.get("secrets_yaml_read") is False and privacy.get("raw_states_persisted") is False
    add("privacy", "Confidentialité du scan", "pass" if privacy_ok else "fail", "secrets.yaml non lu et états bruts non persistés" if privacy_ok else "Vérifier les garanties de confidentialité")
    add("graph", "Graphe de dépendances", "pass", f"{graph_meta.get('service_references_removed', 0)} appel(s) de service filtré(s)")

    counts = plan.get("counts") or {}
    summary_counts = summary.get("priority_counts") or {}
    consistent = all(int(counts.get(k, 0) or 0) == int(summary_counts.get(k, 0) or 0) for k in ("action_now", "verify", "optimize"))
    add("consistency", "Cohérence du rapport", "pass" if consistent else "fail", "Les compteurs du résumé et du plan sont synchronisés" if consistent else "Compteurs incohérents")

    statuses = Counter(x["status"] for x in gates)
    overall = "fail" if statuses.get("fail") else ("warn" if statuses.get("warn") else "pass")
    return {
        "overall": overall,
        "counts": dict(statuses),
        "gates": gates,
    }


def _synchronize_summary(report, plan_items):
    counts = Counter(x.get("priority") for x in plan_items)
    top = [x for x in plan_items if x.get("priority") == "action_now"][:3]
    report["diagnostic_summary"] = {
        "priority_counts": {
            "action_now": counts.get("action_now", 0),
            "verify": counts.get("verify", 0),
            "optimize": counts.get("optimize", 0),
            "info": sum(1 for x in (report.get("diagnostic_explanations") or []) if x.get("priority") == "info"),
        },
        "actionable_count": counts.get("action_now", 0) + counts.get("verify", 0),
        "top_actions": [
            {
                "id": x.get("id"),
                "title": x.get("title"),
                "severity": x.get("severity"),
                "domain": x.get("domain"),
                "confidence": x.get("confidence"),
            }
            for x in top
        ],
        "headline": (
            f"{counts.get('action_now', 0)} correction(s) prioritaire(s), "
            f"{counts.get('verify', 0)} point(s) à vérifier et "
            f"{counts.get('optimize', 0)} optimisation(s)."
        ),
        "source": "final_correlated_action_plan",
    }
    return counts


def _trend_state(score_delta, new_action_now, resolved_count):
    if new_action_now > 0 or (score_delta is not None and score_delta <= -3):
        return "degraded"
    if score_delta is not None and score_delta >= 3:
        return "improved"
    if resolved_count >= 2 and (score_delta is None or score_delta >= 0):
        return "improved"
    return "stable"


def enrich_v070(report, history_path="/data/ha-doctor-history.json"):
    history = load_history(history_path)
    generated_at = report.get("generated_at")
    legacy_score = (report.get("scores") or {}).get("global")

    clean_dependency_graph(report)
    architecture = build_architecture(report)

    explanations = list(report.get("diagnostic_explanations") or [])
    add_dependency_impact(report, explanations)
    add_temporal_context(explanations, history, generated_at)
    explanations.sort(key=_sort_key)
    report["diagnostic_explanations"] = explanations[:60]

    plan_items, suppressed = _plan_explanations(report, explanations)
    score = build_score_v4(report, plan_items, history)
    report["scores"] = {"global": score["global"], "domains": score["domains"]}

    action_items = [_action_item(x) for x in plan_items]
    action_counts = Counter(x.get("priority") for x in plan_items)
    report["action_plan"] = {
        "model": "correlated_action_plan_v2",
        "total": len(action_items),
        "displayed": len(action_items),
        "remaining": 0,
        "counts": {
            "action_now": action_counts.get("action_now", 0),
            "verify": action_counts.get("verify", 0),
            "optimize": action_counts.get("optimize", 0),
        },
        "items": action_items,
        "top": action_items[:6],
        "suppressed_noise": suppressed,
        "note": "Le plan 0.7 est construit après corrélation, déduplication, pondération de confiance, persistance et impact réel des dépendances.",
    }

    _synchronize_summary(report, plan_items)

    current_ids = [str(x.get("id")) for x in plan_items if x.get("id")]
    current_set = set(current_ids)
    previous_ids = set(history[-1].get("active_ids") or []) if history else set()
    new_ids = sorted(current_set - previous_ids) if history else []
    persistent_ids = sorted(current_set & previous_ids) if history else []
    resolved_ids = sorted(previous_ids - current_set) if history else []

    root_causes = [x for x in plan_items if str(x.get("source_type") or "").startswith("registry_")]
    observations = report.get("registry_observations") or []
    report["root_cause_summary"] = {
        "actionable_registry_incidents": len(root_causes),
        "integration_incidents": sum(1 for x in root_causes if x.get("source_type") == "registry_integration"),
        "device_incidents": sum(1 for x in root_causes if x.get("source_type") == "registry_device"),
        "cluster_incidents": sum(1 for x in root_causes if x.get("source_type") == "registry_cluster"),
        "transient_observations": len(observations),
        "noise_suppressed": len(suppressed),
    }

    previous_score = score["previous_score"]
    score_delta = None if previous_score is None else score["global"] - int(previous_score)
    new_action_now = sum(1 for x in plan_items if x.get("id") in set(new_ids) and x.get("priority") == "action_now")
    trend_state = _trend_state(score_delta, new_action_now, len(resolved_ids))

    score_history = []
    for snap in history[-11:]:
        hist_score = snap.get("health_score_v4")
        if hist_score is None:
            hist_score = snap.get("health_score_v3")
        if hist_score is not None:
            score_history.append({"generated_at": snap.get("generated_at"), "score": hist_score})
    score_history.append({"generated_at": generated_at, "score": score["global"]})

    report["temporal_analysis"] = {
        "enabled": True,
        "model": "temporal_v2",
        "history_limit": HISTORY_LIMIT,
        "scan_count": min(HISTORY_LIMIT, len(history) + 1),
        "previous_score": previous_score,
        "score_delta": score_delta,
        "new_count": len(new_ids),
        "persistent_count": len(persistent_ids),
        "resolved_since_previous_count": len(resolved_ids),
        "new_ids": new_ids[:20],
        "persistent_ids": persistent_ids[:20],
        "resolved_since_previous": resolved_ids[:20],
        "score_history": score_history,
        "trend_state": trend_state,
        "new_action_now_count": new_action_now,
        "note": "L'historique conserve uniquement scores, compteurs et identifiants de diagnostics ; aucune valeur brute d'état n'est stockée.",
    }

    report["regression_analysis"] = {
        "state": trend_state,
        "score_delta": score_delta,
        "new_diagnostic_count": len(new_ids),
        "new_action_now_count": new_action_now,
        "resolved_count": len(resolved_ids),
        "persistent_count": len(persistent_ids),
        "requires_attention": trend_state == "degraded",
        "message": (
            "Une régression significative est détectée." if trend_state == "degraded" else
            "La situation s'améliore par rapport aux scans précédents." if trend_state == "improved" else
            "La situation est globalement stable."
        ),
    }

    maintenance = build_maintenance_debt(report)
    report["maintenance_debt"] = maintenance

    report["score_meta"] = {
        "model": "root_cause_temporal_v4",
        "alpha": True,
        "legacy_global": legacy_score,
        "previous_global": previous_score,
        "root_cause_scoring": True,
        "temporal_scoring": True,
        "dependency_scoring": True,
        "raw_entity_volume_scoring": False,
        "helper_fanout_discounted": True,
        "category_penalty_caps": True,
        "penalty_total": score["penalty_total"],
        "domain_penalties": score["domain_penalties"],
        "penalty_breakdown": score["breakdown"][:20],
        "note": "0.7 pondère les causes racines par confiance, persistance et blast radius réel. Les helpers partagés et volumes bruts d'entités ne gonflent plus artificiellement le score.",
    }

    top = [x for x in plan_items if x.get("priority") == "action_now"][:3]
    top_titles = [str(x.get("title")) for x in top if x.get("title")]
    summary_sentences = [f"Indice de santé V4 {score['global']}/100 ({_health_label(score['global'])})."]
    summary_sentences.append(
        f"{action_counts.get('action_now', 0)} correction(s) prioritaire(s), "
        f"{action_counts.get('verify', 0)} point(s) à vérifier et "
        f"{action_counts.get('optimize', 0)} optimisation(s) après corrélation."
    )
    summary_sentences.append(
        f"Architecture {architecture.get('complexity_label', '').lower()} : "
        f"{architecture.get('shared_actuator_count', 0)} actionneur(s) partagé(s) et "
        f"{architecture.get('closed_loop_count', 0)} boucle(s) de contrôle détectée(s)."
    )
    if score_delta is not None:
        summary_sentences.append(f"Évolution depuis le scan précédent : {score_delta:+d} point(s).")
    if resolved_ids:
        summary_sentences.append(f"{len(resolved_ids)} diagnostic(s) ont disparu depuis le scan précédent.")
    if top_titles:
        summary_sentences.append("Priorités : " + " ; ".join(top_titles) + ".")

    report["executive_summary"] = {
        "health_score": score["global"],
        "health_label": _health_label(score["global"]),
        "text": " ".join(summary_sentences),
        "top_priority_titles": top_titles,
        "registry_available": bool((report.get("registry_analysis") or {}).get("available")),
        "root_cause_count": len(root_causes),
        "complexity_score": architecture.get("complexity_score"),
        "complexity_label": architecture.get("complexity_label"),
        "trend_state": trend_state,
        "maintenance_debt_score": maintenance.get("score"),
    }

    report["recommendation_queue"] = {
        "total": len(action_items),
        "items": action_items[:8],
        "strategy": "Corriger d'abord les diagnostics action_now, puis les causes persistantes à forte confiance ou fort impact.",
    }

    report["report_schema"] = {
        "version": REPORT_SCHEMA_VERSION,
        "backward_compatible_with": ["0.5", "0.6"],
        "capabilities": [
            "root_cause_correlation", "temporal_regression", "dependency_blast_radius",
            "architecture_hotspots", "maintenance_debt", "quality_gates",
            "anonymized_export", "read_only_registry_analysis",
        ],
    }

    engine = dict(report.get("diagnostic_engine") or {})
    engine.update({
        "version": "explain_v3_architecture",
        "root_cause_calibration": "root_cause_v3",
        "temporal_analysis": True,
        "dependency_impact_analysis": True,
        "architecture_analysis": True,
        "regression_analysis": True,
        "maintenance_debt_analysis": True,
        "plan_noise_suppressed_count": len(suppressed),
        "registry_incident_count": len(root_causes),
        "external_ai_used": False,
        "automatic_fix": False,
        "read_only": True,
    })
    report["diagnostic_engine"] = engine

    report.setdefault("privacy", {})["temporal_history_raw_states_persisted"] = False
    report["privacy"]["temporal_history_secret_values_persisted"] = False
    report["privacy"]["temporal_history_scope"] = "diagnostic_ids_counts_scores_only"
    report["privacy"]["architecture_raw_state_values_persisted"] = False
    report["privacy"]["automatic_configuration_changes"] = False

    # Quality gates are evaluated last so report-count consistency can be checked.
    report["quality_gates"] = build_quality_gates(report)

    snapshot = {
        "generated_at": generated_at,
        "health_score_v4": score["global"],
        "health_score_v3": None,
        "legacy_score": legacy_score,
        "active_ids": current_ids,
        "registry_ids": [str(x.get("id")) for x in root_causes if x.get("id")],
        "priority_counts": report["action_plan"]["counts"],
        "unavailable_count": (report.get("inventory") or {}).get("unavailable_count"),
        "unknown_count": (report.get("inventory") or {}).get("unknown_count"),
        "architecture": {
            "complexity_score": architecture.get("complexity_score"),
            "shared_actuator_count": architecture.get("shared_actuator_count"),
            "closed_loop_count": architecture.get("closed_loop_count"),
        },
        "maintenance_debt_score": maintenance.get("score"),
    }
    history.append(snapshot)
    save_history(history, history_path)

    report["version"] = VERSION
    return report
