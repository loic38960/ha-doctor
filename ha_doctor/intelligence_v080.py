"""HA Doctor 0.8 intelligence layer.

0.8 keeps the proven 0.7 root-cause and temporal engine, then upgrades:
- semantic entity-flow with dynamic target resolution
- explicit call edges for scripts/scenes/automations
- automation coverage reconciliation against runtime health
- dependency blast radius V2 using the richer flow graph
- architecture risk V2 with capped/logarithmic read fan-out
- maintenance debt V2 with duplicate-count protection
- stronger quality gates and report schema

The health score remains on the 0.7 V4 scale for temporal continuity.
"""

from collections import Counter, defaultdict
import math

import intelligence_v070 as v070
from flow_v080 import enrich_dependency_graph
from temporal_v060 import load_history, save_history

VERSION = "0.8.0"
REPORT_SCHEMA_VERSION = "ha-doctor-report/0.8"

PRIORITY_ORDER = {"action_now": 0, "verify": 1, "optimize": 2, "info": 3}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

HIGH_CONSEQUENCE_DOMAINS = {"alarm_control_panel", "lock", "siren"}
ACTUATOR_DOMAINS = set(v070.ACTUATOR_DOMAINS)
HELPER_DOMAINS = set(v070.HELPER_DOMAINS)
SENSOR_DOMAINS = set(v070.SENSOR_DOMAINS)
OPTIONAL_DOMAINS = set(v070.OPTIONAL_DOMAINS)


def _domain(entity_id):
    value = str(entity_id or "")
    return value.split(".", 1)[0] if "." in value else ""


def _kind(entity_id):
    return v070._kind(entity_id)


def _find_finding(report, rule_id):
    for item in report.get("findings") or []:
        if str(item.get("rule_id") or "") == rule_id:
            return item
    return None


def build_automation_coverage(report):
    """Measure coverage against healthy runtime automations, not stale unavailable ones."""
    inventory = report.get("inventory") or {}
    yaml_count = int(inventory.get("automations_detected", 0) or 0)
    state_total = int((inventory.get("domains") or {}).get("automation", 0) or 0)

    runtime_total = state_total
    runtime_healthy = None
    runtime_unavailable = 0
    runtime_unknown = 0

    registry = report.get("registry_analysis") or {}
    for group in ((registry.get("integration_health") or {}).get("groups") or []):
        if str(group.get("integration") or "") == "automation":
            runtime_total = int(group.get("total", state_total) or 0)
            runtime_healthy = int(group.get("healthy", 0) or 0)
            runtime_unavailable = int(group.get("unavailable", 0) or 0)
            runtime_unknown = int(group.get("unknown", 0) or 0)
            break

    if runtime_healthy is None:
        unavailable_group = 0
        for group in ((report.get("entity_health") or {}).get("unavailable") or {}).get("groups") or []:
            if str(group.get("key") or "") == "automation":
                unavailable_group = int(group.get("count", 0) or 0)
                break
        runtime_unavailable = unavailable_group
        runtime_healthy = max(0, runtime_total - runtime_unavailable - runtime_unknown)

    expected_analyzable = runtime_healthy if runtime_healthy > 0 else runtime_total
    ratio = (
        min(1.0, yaml_count / expected_analyzable)
        if expected_analyzable > 0
        else (1.0 if yaml_count == 0 else 0.0)
    )
    gap = max(0, expected_analyzable - yaml_count)
    extra = max(0, yaml_count - expected_analyzable)

    orphan = (registry.get("orphan_analysis") or {})
    local_candidates = orphan.get("local_unavailable_candidates") or orphan.get("candidates") or []
    stale_automation_candidates = sum(
        1
        for item in local_candidates
        if str(item.get("platform") or "") == "automation"
        or str(item.get("entity_id") or "").startswith("automation.")
    )

    coverage = {
        "model": "automation_coverage_v2",
        "yaml_automations_analyzed": yaml_count,
        "runtime_automation_entities": runtime_total,
        "runtime_healthy_automations": runtime_healthy,
        "runtime_unavailable_automations": runtime_unavailable,
        "runtime_unknown_automations": runtime_unknown,
        "expected_analyzable_automations": expected_analyzable,
        "coverage_ratio": round(ratio, 3),
        "coverage_percent": round(ratio * 100.0, 1),
        "coverage_gap": gap,
        "yaml_extra_count": extra,
        "stale_registry_automation_candidates": stale_automation_candidates,
        "unavailable_registry_entries_count_as_coverage_gap": False,
        "interpretation": (
            "La couverture compare les automatisations YAML analysées aux automatisations "
            "runtime actuellement disponibles. Les anciennes entrées registry unavailable "
            "sont suivies séparément."
        ),
    }
    report["automation_coverage"] = coverage

    finding = _find_finding(report, "HD-CFG-005")
    if finding:
        finding["title"] = "Couverture des automatisations chargées"
        finding["summary"] = (
            f"HA Doctor analyse {yaml_count} automatisation(s) YAML pour "
            f"{expected_analyzable} automatisation(s) runtime disponible(s) "
            f"({coverage['coverage_percent']} %). "
            f"{runtime_unavailable} entrée(s) automation unavailable sont suivies séparément."
        )
        finding["recommendation"] = (
            "Traiter un éventuel écart de couverture uniquement sur les automatisations "
            "runtime disponibles. Ne pas compter automatiquement les anciennes entrées "
            "unavailable comme des automatisations non analysées."
        )

    for explanation in report.get("diagnostic_explanations") or []:
        if str(explanation.get("source_id") or "") == "HD-CFG-005":
            explanation["title"] = "Couverture des automatisations chargées"
            explanation["diagnosis"] = (
                f"{yaml_count} automatisation(s) YAML sont analysées pour "
                f"{expected_analyzable} automatisation(s) runtime actuellement disponibles."
            )
            explanation["impact"] = (
                "Cette métrique mesure la couverture réelle du moteur statique sans confondre "
                "les anciennes entrées registry unavailable avec un trou d'analyse."
            )
            explanation["evidence"] = [{
                "type": "coverage",
                "label": "Couverture",
                "text": (
                    f"{yaml_count}/{expected_analyzable} disponibles · "
                    f"{runtime_unavailable} unavailable séparées"
                ),
            }]
            explanation["resolution_goal"] = "Maintenir une couverture proche de 100 % des automatisations runtime disponibles."
            explanation["safe_to_ignore_when"] = (
                "Aucune action si la couverture est complète ; les entrées unavailable sont un sujet de maintenance séparé."
            )

    return coverage


def _control_confidence(node):
    confidence = {str(entity_id): 1.0 for entity_id in node.get("controls") or []}
    for item in node.get("dynamic_controls") or []:
        entity_id = str(item.get("entity_id") or "")
        if entity_id:
            confidence[entity_id] = min(
                confidence.get(entity_id, 1.0),
                float(item.get("confidence", 0.0) or 0.0),
            )
    return confidence


def _risk_label(score):
    if score >= 18:
        return "Élevé"
    if score >= 10:
        return "Renforcé"
    if score >= 5:
        return "Modéré"
    return "Faible"


def build_architecture_v2(report):
    """Rebuild architecture from the V3 flow graph.

    Read fan-out is logarithmic/capped. Physical controls dominate risk.
    """
    graph = report.get("dependency_graph") or []
    meta = report.get("dependency_graph_meta") or {}
    by_entity = defaultdict(lambda: {
        "triggers": set(),
        "controls": set(),
        "reads": set(),
        "calls": set(),
        "references": set(),
        "control_confidence": {},
    })
    source_counts = Counter()
    automation_profiles = []
    closed_loops = []

    for node in graph:
        name = str(node.get("automation") or "Automatisation")
        source = str(node.get("source") or "")
        if source:
            source_counts[source] += 1

        triggers = set(node.get("triggers_on") or [])
        controls = set(node.get("controls") or [])
        reads = set(node.get("reads") or [])
        calls = set(node.get("calls") or [])
        refs = set(node.get("references") or [])
        confidence = _control_confidence(node)

        for entity_id in triggers:
            by_entity[entity_id]["triggers"].add(name)
        for entity_id in controls:
            by_entity[entity_id]["controls"].add(name)
            by_entity[entity_id]["control_confidence"][name] = confidence.get(entity_id, 1.0)
        for entity_id in reads:
            by_entity[entity_id]["reads"].add(name)
        for entity_id in calls:
            by_entity[entity_id]["calls"].add(name)
        for entity_id in refs:
            by_entity[entity_id]["references"].add(name)

        self_entities = sorted(triggers & controls)
        if self_entities:
            closed_loops.append({
                "automation": name,
                "source": source,
                "entities": self_entities[:10],
                "count": len(self_entities),
            })

        actuator_controls = [
            entity_id for entity_id in controls if _kind(entity_id) == "actuator"
        ]
        helper_controls = [
            entity_id for entity_id in controls if _kind(entity_id) == "helper"
        ]
        possible_controls = [
            item for item in (node.get("dynamic_controls") or [])
            if float(item.get("confidence", 0) or 0) < 0.85
        ]

        physical_score = 0.0
        for entity_id in actuator_controls:
            conf = confidence.get(entity_id, 1.0)
            domain = _domain(entity_id)
            weight = 6.0
            if domain in HIGH_CONSEQUENCE_DOMAINS:
                weight = 8.0
            elif domain in {"cover", "climate", "switch", "lawn_mower", "vacuum"}:
                weight = 6.5
            physical_score += weight * conf

        # Large readers should not outrank safety/actuator automations simply
        # because they inspect many entities.
        read_score = min(3.0, math.log2(1 + len(reads)) * 0.75) if reads else 0.0
        trigger_score = min(8.0, len(triggers) * 1.15)
        helper_score = min(4.0, len(helper_controls) * 0.85)
        call_score = min(2.5, math.log2(1 + len(calls)) * 0.65) if calls else 0.0
        loop_score = 4.5 if self_entities else 0.0
        unresolved_score = min(2.5, len(node.get("unresolved_dynamic_targets") or []) * 0.7)

        risk = (
            physical_score
            + trigger_score
            + helper_score
            + read_score
            + call_score
            + loop_score
            + unresolved_score
        )

        automation_profiles.append({
            "automation": name,
            "source": source,
            "trigger_count": len(triggers),
            "control_count": len(controls),
            "actuator_control_count": len(actuator_controls),
            "helper_control_count": len(helper_controls),
            "call_count": len(calls),
            "read_count": len(reads),
            "possible_control_count": len(possible_controls),
            "unresolved_dynamic_target_count": len(node.get("unresolved_dynamic_targets") or []),
            "self_feedback": bool(self_entities),
            "risk_index": round(risk, 1),
            "risk_label": _risk_label(risk),
            "actuators": sorted(actuator_controls)[:10],
            "calls": sorted(calls)[:8],
        })

    hotspots = []
    for entity_id, relations in by_entity.items():
        kind = _kind(entity_id)
        trigger_count = len(relations["triggers"])
        control_count = len(relations["controls"])
        read_count = len(relations["reads"])
        call_count = len(relations["calls"])
        ref_count = len(relations["references"])
        avg_conf = (
            sum(relations["control_confidence"].values()) / len(relations["control_confidence"])
            if relations["control_confidence"]
            else 1.0
        )

        kind_weight = {
            "actuator": 1.35,
            "sensor": 1.0,
            "helper": 0.42,
            "optional": 0.35,
        }.get(kind, 0.65)
        raw = (
            trigger_count * 2.5
            + control_count * (5.5 if kind == "actuator" else 1.7) * avg_conf
            + min(3.0, math.log2(1 + read_count) * 0.8 if read_count else 0.0)
            + call_count * 0.6
            + min(2.0, ref_count * 0.15)
        ) * kind_weight

        hotspots.append({
            "entity_id": entity_id,
            "kind": kind,
            "triggered_automations": trigger_count,
            "controlling_automations": control_count,
            "reading_automations": read_count,
            "calling_automations": call_count,
            "referencing_automations": ref_count,
            "average_control_confidence": round(avg_conf, 2),
            "criticality": min(100, int(round(raw * 4.0))),
            "controllers": sorted(relations["controls"])[:10],
            "triggers": sorted(relations["triggers"])[:10],
            "callers": sorted(relations["calls"])[:10],
        })

    hotspots.sort(key=lambda item: (-item["criticality"], item["entity_id"]))
    automation_profiles.sort(key=lambda item: (-item["risk_index"], item["automation"]))

    shared_actuators = [
        item for item in hotspots
        if item["kind"] == "actuator" and item["controlling_automations"] > 1
    ]
    helper_hubs = [
        item for item in hotspots
        if item["kind"] == "helper" and item["controlling_automations"] > 1
    ]
    trigger_hubs = [
        item for item in hotspots if item["triggered_automations"] >= 3
    ]
    call_hubs = [
        item for item in hotspots if item["calling_automations"] >= 3
    ]
    critical_dependencies = [
        item for item in hotspots
        if item["kind"] in {"sensor", "helper"}
        and (
            item["triggered_automations"] >= 4
            or item["referencing_automations"] >= 7
        )
    ]

    states = int((report.get("inventory") or {}).get("states", 0) or 0)
    integrations = int(
        (((report.get("registry_analysis") or {}).get("integration_health") or {}).get("total", 0) or 0)
    )
    edges = int(meta.get("entity_edges", 0) or 0)
    controls = int(meta.get("control_edges", 0) or 0)
    calls = int(meta.get("call_edges", 0) or 0)
    unresolved = int(meta.get("unresolved_dynamic_target_count", 0) or 0)
    complexity = min(
        100,
        int(round(
            states / 95.0
            + len(graph) * 0.32
            + integrations * 0.22
            + edges * 0.02
            + controls * 0.06
            + calls * 0.03
            + unresolved * 0.4
        )),
    )
    if complexity >= 75:
        complexity_label = "Très complexe"
    elif complexity >= 55:
        complexity_label = "Avancée"
    elif complexity >= 35:
        complexity_label = "Intermédiaire"
    else:
        complexity_label = "Simple"

    architecture = {
        "model": "architecture_v2_flow",
        "complexity_score": complexity,
        "complexity_label": complexity_label,
        "automation_count": len(graph),
        "entity_dependency_count": len(by_entity),
        "entity_edge_count": edges,
        "control_edge_count": controls,
        "call_edge_count": calls,
        "dynamic_target_resolution_rate": meta.get("dynamic_target_resolution_rate"),
        "target_resolution_rate": meta.get("target_resolution_rate"),
        "unresolved_dynamic_target_count": unresolved,
        "shared_actuator_count": len(shared_actuators),
        "helper_hub_count": len(helper_hubs),
        "trigger_hub_count": len(trigger_hubs),
        "call_hub_count": len(call_hubs),
        "critical_dependency_count": len(critical_dependencies),
        "closed_loop_count": len(closed_loops),
        "top_hotspots": hotspots[:25],
        "shared_actuators": shared_actuators[:20],
        "helper_hubs": helper_hubs[:20],
        "trigger_hubs": trigger_hubs[:20],
        "call_hubs": call_hubs[:20],
        "critical_dependencies": critical_dependencies[:20],
        "closed_loops": closed_loops[:20],
        "automation_risk_profiles": automation_profiles[:25],
        "top_sources": [
            {"source": source, "automation_count": count}
            for source, count in source_counts.most_common(20)
        ],
        "risk_model_note": (
            "Le risque architectural privilégie les commandes physiques, boucles et cibles "
            "incertaines. Le fan-out de lecture est logarithmique et plafonné."
        ),
        "note": "La complexité décrit l'architecture ; elle ne réduit pas directement l'indice de santé.",
    }
    report["architecture_analysis"] = architecture
    return architecture


def _explanation_entities(report, item):
    try:
        return set(v070._explanation_entities(report, item))
    except Exception:
        return set()


def add_dependency_impact_v2(report):
    """Recompute diagnostic blast radius from controls/calls/dynamic targets."""
    graph = report.get("dependency_graph") or []
    architecture = report.get("architecture_analysis") or {}
    risk_by_automation = {
        str(item.get("automation") or ""): float(item.get("risk_index", 0) or 0)
        for item in architecture.get("automation_risk_profiles") or []
    }

    explanations = report.get("diagnostic_explanations") or []
    impact_by_id = {}

    for item in explanations:
        entities = _explanation_entities(report, item)
        impacted = set()
        high_risk = set()
        helper_only = set()
        trigger_hits = 0
        control_hits = 0
        call_hits = 0
        read_hits = 0
        possible_control_hits = 0
        weighted = 0.0
        top_entities = []

        for entity_id in entities:
            kind = _kind(entity_id)
            local_impacted = set()
            local_weight = 0.0
            local_trigger = 0
            local_control = 0
            local_call = 0
            local_read = 0
            local_possible = 0

            for node in graph:
                name = str(node.get("automation") or "Automatisation")
                triggers = set(node.get("triggers_on") or [])
                controls = set(node.get("controls") or [])
                reads = set(node.get("reads") or [])
                calls = set(node.get("calls") or [])
                dynamic = {
                    str(entry.get("entity_id") or ""): float(entry.get("confidence", 0) or 0)
                    for entry in node.get("dynamic_controls") or []
                }

                relation_weight = 0.0
                if entity_id in triggers:
                    local_trigger += 1
                    relation_weight += 2.3
                if entity_id in controls:
                    local_control += 1
                    conf = dynamic.get(entity_id, 1.0)
                    relation_weight += 2.0 * conf
                    if conf < 0.85:
                        local_possible += 1
                if entity_id in calls:
                    local_call += 1
                    relation_weight += 1.0
                if entity_id in reads:
                    local_read += 1
                    relation_weight += 0.85

                if relation_weight > 0:
                    local_impacted.add(name)
                    if risk_by_automation.get(name, 0.0) >= 10:
                        high_risk.add(name)
                    if kind == "helper" and entity_id not in triggers:
                        helper_only.add(name)
                    local_weight += relation_weight

            kind_factor = {
                "actuator": 1.35,
                "sensor": 1.0,
                "helper": 0.45,
                "optional": 0.35,
            }.get(kind, 0.7)
            local_weight *= kind_factor
            impacted.update(local_impacted)
            trigger_hits += local_trigger
            control_hits += local_control
            call_hits += local_call
            read_hits += local_read
            possible_control_hits += local_possible
            weighted += local_weight
            if local_impacted:
                top_entities.append({
                    "entity_id": entity_id,
                    "kind": kind,
                    "automation_count": len(local_impacted),
                    "trigger_hits": local_trigger,
                    "control_hits": local_control,
                    "call_hits": local_call,
                    "read_hits": local_read,
                    "weight": round(local_weight, 2),
                })

        top_entities.sort(key=lambda entry: (-entry["weight"], entry["entity_id"]))
        if weighted >= 22 or len(high_risk) >= 5:
            level = "high"
            multiplier = 1.15
        elif weighted >= 5 or len(high_risk) >= 2:
            level = "medium"
            multiplier = 1.07
        else:
            level = "low"
            multiplier = 1.0

        impact = {
            "model": "blast_radius_v2_flow",
            "level": level,
            "impacted_automation_count": len(impacted),
            "high_risk_automation_count": len(high_risk),
            "helper_only_automation_count": len(helper_only),
            "impacted_automations": sorted(impacted)[:15],
            "high_risk_automations": sorted(high_risk)[:12],
            "trigger_dependency_count": trigger_hits,
            "control_dependency_count": control_hits,
            "call_dependency_count": call_hits,
            "read_dependency_count": read_hits,
            "possible_control_dependency_count": possible_control_hits,
            "weighted_impact_score": round(weighted, 2),
            "score_multiplier": multiplier,
            "top_entities": top_entities[:10],
            "helper_fanout_discounted": True,
            "dynamic_control_confidence_applied": True,
        }
        item["dependency_impact"] = impact
        impact_by_id[str(item.get("id") or "")] = impact

    def patch_items(items):
        for entry in items or []:
            diagnostic_id = str(entry.get("id") or "")
            if diagnostic_id in impact_by_id:
                entry["dependency_impact"] = impact_by_id[diagnostic_id]
                impact = impact_by_id[diagnostic_id]
                if entry.get("priority") == "verify" and impact.get("level") == "high":
                    entry["why_now"] = (
                        "Diagnostic persistant avec un impact élevé sur le graphe de dépendances."
                    )

    action_plan = report.get("action_plan") or {}
    patch_items(action_plan.get("items"))
    patch_items(action_plan.get("top"))
    action_plan["model"] = "correlated_action_plan_v3_flow"

    queue = report.get("recommendation_queue") or {}
    patch_items(queue.get("items"))
    queue["strategy"] = (
        "Corriger d'abord les action_now, puis les causes persistantes à forte confiance "
        "ou à blast radius élevé selon le graphe V3."
    )

    score_meta = report.get("score_meta") or {}
    for entry in score_meta.get("penalty_breakdown") or []:
        diagnostic_id = str(entry.get("id") or "")
        if diagnostic_id in impact_by_id:
            entry["dependency_impact"] = impact_by_id[diagnostic_id].get("level")
    score_meta["dependency_scoring_model"] = "blast_radius_v2_flow"
    score_meta["score_recomputed_after_flow_upgrade"] = False
    score_meta["score_continuity_note"] = (
        "0.8 conserve l'échelle V4 de 0.7 pour ne pas casser l'historique ; le blast radius "
        "affiché est recalculé avec le graphe V3."
    )
    return impact_by_id


def build_maintenance_debt_v2(report):
    findings = report.get("findings") or []
    registry = report.get("registry_analysis") or {}
    orphan = registry.get("orphan_analysis") or {}
    coverage = report.get("automation_coverage") or {}

    missing_reference_count = 0
    archived_secret_hint_count = 0
    active_secret_hint_count = 0
    duplicate_writer_pairs = 0
    duplicate_action_count = 0
    long_wait_count = 0

    for finding in findings:
        rule_id = str(finding.get("rule_id") or "")
        examples = finding.get("examples") or []
        if rule_id == "HD-CFG-001":
            missing_reference_count = len(examples)
        elif rule_id == "HD-SEC-003":
            archived_secret_hint_count = len(examples)
        elif rule_id == "HD-SEC-001":
            active_secret_hint_count = len(examples)
        elif rule_id == "HD-AUTO-009":
            duplicate_writer_pairs = len(examples)
        elif rule_id == "HD-AUTO-005":
            duplicate_action_count = len(examples)
        elif rule_id in {"HD-AUTO-001", "HD-AUTO-002"}:
            long_wait_count += len(examples)

    probable_orphan_count = int(
        orphan.get("probable_orphan_count", orphan.get("high_confidence_count", 0)) or 0
    )
    review_candidate_count = int(
        orphan.get("review_candidate_count", orphan.get("candidate_count", 0)) or 0
    )
    coverage_gap = int(coverage.get("coverage_gap", 0) or 0)
    stale_automation_candidates = int(
        coverage.get("stale_registry_automation_candidates", 0) or 0
    )

    components = {
        "broken_references": min(25.0, missing_reference_count * 2.2),
        "probable_orphans": min(20.0, probable_orphan_count * 4.0),
        "registry_review": min(14.0, review_candidate_count * 0.35),
        "archived_security": min(12.0, archived_secret_hint_count * 0.9),
        "coverage_gap": min(18.0, coverage_gap * 3.0),
        "automation_hygiene": min(
            16.0,
            duplicate_writer_pairs * 6.0
            + duplicate_action_count * 2.5
            + long_wait_count * 0.6,
        ),
    }
    score = int(round(min(100.0, sum(components.values()))))

    if score >= 70:
        label = "Très élevée"
    elif score >= 50:
        label = "Élevée"
    elif score >= 25:
        label = "Modérée"
    else:
        label = "Faible"

    maintenance = {
        "model": "maintenance_debt_v2",
        "score": score,
        "label": label,
        "components": {key: round(value, 1) for key, value in components.items()},
        "missing_reference_count": missing_reference_count,
        "probable_orphan_count": probable_orphan_count,
        "local_review_candidate_count": review_candidate_count,
        "stale_registry_automation_candidates": stale_automation_candidates,
        "archived_secret_hint_count": archived_secret_hint_count,
        "active_secret_hint_count": active_secret_hint_count,
        "duplicate_writer_pair_count": duplicate_writer_pairs,
        "duplicate_action_count": duplicate_action_count,
        "long_wait_signal_count": long_wait_count,
        "automation_coverage_ratio": coverage.get("coverage_ratio"),
        "automation_coverage_gap": coverage_gap,
        "unavailable_automations_double_counted": False,
        "double_count_protection": True,
        "confidence": "medium" if review_candidate_count else "high",
        "note": (
            "La dette V2 sépare couverture réelle, candidats registry, références cassées et "
            "hygiène d'automatisation. Un candidat faible n'est plus pénalisé comme un orphelin confirmé."
        ),
    }
    report["maintenance_debt"] = maintenance
    return maintenance


def _gate(key, label, status, detail):
    return {"key": key, "label": label, "status": status, "detail": detail}


def build_quality_gates_v2(report):
    old = report.get("quality_gates") or {}
    old_by_key = {
        str(item.get("key") or ""): item
        for item in old.get("gates") or []
        if isinstance(item, dict)
    }
    meta = report.get("dependency_graph_meta") or {}
    coverage = report.get("automation_coverage") or {}
    temporal = report.get("temporal_analysis") or {}

    gates = []
    for key in ("api", "yaml", "blueprints", "registry", "privacy", "consistency"):
        if key in old_by_key:
            gates.append(old_by_key[key])

    target_rate = float(meta.get("target_resolution_rate", 1.0) or 0.0)
    dynamic_rate = float(meta.get("dynamic_target_resolution_rate", 1.0) or 0.0)
    semantic_rate = float(meta.get("semantic_match_rate", 1.0) or 0.0)
    unresolved = int(meta.get("unresolved_dynamic_target_count", 0) or 0)
    parse_errors = len(meta.get("flow_reparse_errors") or [])

    if target_rate >= 0.92 and semantic_rate >= 0.95 and parse_errors == 0:
        flow_status = "pass"
    elif target_rate >= 0.75 and semantic_rate >= 0.80:
        flow_status = "warning"
    else:
        flow_status = "fail"
    gates.append(_gate(
        "flow",
        "Résolution des flux d'entités",
        flow_status,
        (
            f"{target_rate * 100:.1f} % des cibles comprises · "
            f"{dynamic_rate * 100:.1f} % des cibles dynamiques · "
            f"{unresolved} non résolue(s)"
        ),
    ))

    coverage_ratio = float(coverage.get("coverage_ratio", 1.0) or 0.0)
    coverage_gap = int(coverage.get("coverage_gap", 0) or 0)
    if coverage_ratio >= 0.95:
        coverage_status = "pass"
    elif coverage_ratio >= 0.85:
        coverage_status = "warning"
    else:
        coverage_status = "fail"
    gates.append(_gate(
        "automation_coverage",
        "Couverture des automatisations",
        coverage_status,
        (
            f"{coverage.get('yaml_automations_analyzed', 0)}/"
            f"{coverage.get('expected_analyzable_automations', 0)} runtime disponibles · "
            f"écart {coverage_gap}"
        ),
    ))

    temporal_enabled = bool(temporal.get("enabled"))
    history_count = int(temporal.get("scan_count", 0) or 0)
    gates.append(_gate(
        "temporal",
        "Historique temporel",
        "pass" if temporal_enabled else "warning",
        f"{history_count} scan(s) corrélés · états bruts non stockés",
    ))

    counts = Counter(str(item.get("status") or "warning") for item in gates)
    if counts.get("fail"):
        overall = "fail"
    elif counts.get("warning"):
        overall = "warning"
    else:
        overall = "pass"

    quality = {
        "model": "quality_gates_v2",
        "overall": overall,
        "counts": dict(counts),
        "gates": gates,
    }
    report["quality_gates"] = quality
    return quality


def _sync_summary(report):
    coverage = report.get("automation_coverage") or {}
    meta = report.get("dependency_graph_meta") or {}
    architecture = report.get("architecture_analysis") or {}
    maintenance = report.get("maintenance_debt") or {}
    executive = report.get("executive_summary") or {}

    existing = str(executive.get("text") or "").strip()
    suffix = (
        f" Flux V3 : {float(meta.get('target_resolution_rate', 1.0) or 0.0) * 100:.1f} % "
        f"des cibles comprises ; couverture automations chargées "
        f"{float(coverage.get('coverage_ratio', 1.0) or 0.0) * 100:.1f} %. "
        f"Dette maintenance V2 : {maintenance.get('score', 0)}/100 ({maintenance.get('label', 'n/a')})."
    )
    if "Flux V3 :" not in existing:
        executive["text"] = (existing + suffix).strip()
    executive["complexity_score"] = architecture.get("complexity_score")
    executive["complexity_label"] = architecture.get("complexity_label")
    executive["maintenance_debt_score"] = maintenance.get("score")
    executive["flow_target_resolution_rate"] = meta.get("target_resolution_rate")
    executive["automation_coverage_ratio"] = coverage.get("coverage_ratio")

    engine = report.get("diagnostic_engine") or {}
    engine.update({
        "version": "explain_v4_entity_flow",
        "dynamic_target_analysis": True,
        "script_call_graph": True,
        "automation_coverage_reconciliation": True,
        "maintenance_debt_v2": True,
        "architecture_analysis": True,
        "read_fanout_capped": True,
        "raw_dynamic_template_text_persisted": False,
    })

    privacy = report.get("privacy") or {}
    privacy.update({
        "flow_engine_raw_yaml_persisted": False,
        "dynamic_target_templates_persisted": False,
        "script_call_payloads_persisted": False,
    })


def _update_history_snapshot(report, history_path):
    """Patch the snapshot just written by 0.7 with 0.8 aggregate metrics only."""
    history = load_history(history_path)
    if not history:
        return
    generated_at = report.get("generated_at")
    if str(history[-1].get("generated_at") or "") != str(generated_at or ""):
        return

    architecture = report.get("architecture_analysis") or {}
    maintenance = report.get("maintenance_debt") or {}
    coverage = report.get("automation_coverage") or {}
    meta = report.get("dependency_graph_meta") or {}

    snapshot = dict(history[-1])
    snapshot["architecture"] = {
        "complexity_score": architecture.get("complexity_score"),
        "shared_actuator_count": architecture.get("shared_actuator_count"),
        "closed_loop_count": architecture.get("closed_loop_count"),
        "call_hub_count": architecture.get("call_hub_count"),
        "critical_dependency_count": architecture.get("critical_dependency_count"),
    }
    snapshot["maintenance_debt_score"] = maintenance.get("score")
    snapshot["flow_target_resolution_rate"] = meta.get("target_resolution_rate")
    snapshot["flow_dynamic_resolution_rate"] = meta.get("dynamic_target_resolution_rate")
    snapshot["automation_coverage_ratio"] = coverage.get("coverage_ratio")
    snapshot["report_version"] = VERSION
    history[-1] = snapshot
    save_history(history, history_path)


def enrich_v080(report, history_path="/data/ha-doctor-history.json"):
    # First run 0.7 exactly as before: root causes, temporal state, score V4,
    # action plan and initial architecture are all preserved.
    report = v070.enrich_v070(report, history_path=history_path)

    enrich_dependency_graph(report)
    coverage = build_automation_coverage(report)
    architecture = build_architecture_v2(report)
    add_dependency_impact_v2(report)
    maintenance = build_maintenance_debt_v2(report)
    build_quality_gates_v2(report)
    _sync_summary(report)

    score_meta = report.get("score_meta") or {}
    score_meta["model"] = "root_cause_temporal_v4_flow_v3"
    score_meta["flow_target_resolution_rate"] = (report.get("dependency_graph_meta") or {}).get("target_resolution_rate")
    score_meta["automation_coverage_ratio"] = coverage.get("coverage_ratio")
    score_meta["maintenance_debt_model"] = maintenance.get("model")
    score_meta["note"] = (
        "0.8 conserve le score de santé V4 pour la continuité temporelle, mais remplace "
        "l'analyse de flux, la couverture, le blast radius, le risque architectural et "
        "la dette de maintenance par les modèles V2/V3."
    )

    report["report_schema"] = {
        "version": REPORT_SCHEMA_VERSION,
        "backward_compatible_with": ["0.5", "0.6", "0.7"],
        "capabilities": [
            "root_cause_correlation",
            "temporal_regression",
            "dependency_blast_radius_v2",
            "semantic_dynamic_target_resolution",
            "script_scene_call_graph",
            "automation_runtime_coverage",
            "architecture_hotspots_v2",
            "critical_dependency_analysis",
            "maintenance_debt_v2",
            "quality_gates_v2",
            "anonymized_export",
            "read_only_registry_analysis",
        ],
    }

    root = report.get("root_cause_summary") or {}
    root["flow_target_resolution_rate"] = (report.get("dependency_graph_meta") or {}).get("target_resolution_rate")
    root["dynamic_target_resolution_rate"] = (report.get("dependency_graph_meta") or {}).get("dynamic_target_resolution_rate")
    root["automation_coverage_ratio"] = coverage.get("coverage_ratio")
    root["shared_actuator_count"] = architecture.get("shared_actuator_count")
    root["critical_dependency_count"] = architecture.get("critical_dependency_count")

    queue = report.get("recommendation_queue") or {}
    queue["model"] = "recommendation_queue_v3_flow"

    report["version"] = VERSION
    _update_history_snapshot(report, history_path)
    return report
