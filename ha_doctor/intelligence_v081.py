"""HA Doctor 0.8.1 report hardening orchestrator."""
from collections import Counter

import intelligence_v080 as v080
from temporal_v060 import load_history, save_history
from snapshot_v081 import synchronize_state_snapshot
from semantics_v081 import build_flow_confidence, build_condition_semantics
from callgraph_v081 import build_transitive_call_graph
from context_v081 import calibrate_operational_context
from resilience_v081 import build_resilience_analysis

VERSION = "0.8.1"
REPORT_SCHEMA_VERSION = "ha-doctor-report/0.8.1"


def sync_action_counts(report):
    plan = report.get("action_plan") or {}
    items = plan.get("items") or []
    counts = Counter(str(x.get("priority") or "info") for x in items)
    plan.update({
        "total": len(items), "displayed": len(items), "remaining": 0,
        "counts": {k: counts.get(k, 0) for k in ("action_now", "verify", "optimize")},
        "model": "correlated_action_plan_v3.1_hardened",
        "note": "Le plan 0.8.1 est reconstruit après corrélation, contexte, confiance de flux et sémantique des conditions.",
        "top": items[:6],
    })
    queue = report.get("recommendation_queue") or {}
    queue.update({"items": list(items), "total": len(items), "model": "recommendation_queue_v3.1_hardened"})
    summary = report.setdefault("diagnostic_summary", {})
    summary.update({
        "priority_counts": {k: counts.get(k, 0) for k in ("action_now", "verify", "optimize", "info")},
        "actionable_count": counts.get("action_now", 0) + counts.get("verify", 0),
        "headline": f"{counts.get('action_now',0)} correction(s) prioritaire(s), {counts.get('verify',0)} point(s) à vérifier et {counts.get('optimize',0)} optimisation(s).",
    })


def rebuild_executive_summary(report):
    score = int((report.get("scores") or {}).get("global", 0) or 0)
    counts = (report.get("action_plan") or {}).get("counts") or {}
    arch = report.get("architecture_analysis") or {}
    conf = report.get("flow_confidence") or {}
    coverage = report.get("automation_coverage") or {}
    sem = report.get("condition_semantics") or {}
    resilience = report.get("resilience_analysis") or {}
    temporal = report.get("temporal_analysis") or {}
    maintenance = report.get("maintenance_debt") or {}
    label = "Bon" if score >= 85 else ("À surveiller" if score >= 70 else "À corriger")
    text = (
        f"Indice de santé V4 {score}/100 ({label}). {counts.get('action_now',0)} correction(s) prioritaire(s), "
        f"{counts.get('verify',0)} point(s) à vérifier et {counts.get('optimize',0)} optimisation(s). "
        f"Architecture : {arch.get('shared_actuator_count',0)} actionneur(s) partagé(s), {arch.get('closed_loop_count',0)} boucle(s) de contrôle et {arch.get('critical_dependency_count',0)} dépendance(s) critique(s). "
        f"Conditions : {sem.get('proven_exclusive_pair_count',0)} paire(s) mutuellement exclusives démontrées. "
        f"Résilience : {resilience.get('review_count',0)} dépendance(s) critique(s) sans fallback statique clair. "
        f"Flux : {float(conf.get('target_resolution_rate',0))*100:.1f}% résolus, {conf.get('low_confidence_dynamic_edges',0)} arête(s) dynamique(s) à confiance réduite ; couverture {float(coverage.get('coverage_ratio',0))*100:.1f}%. "
        f"Dette maintenance : {maintenance.get('score',0)}/100 ({maintenance.get('label','n/a')})."
    )
    report["executive_summary"] = {
        **(report.get("executive_summary") or {}),
        "health_score": score, "health_label": label, "text": text,
        "complexity_score": arch.get("complexity_score"), "complexity_label": arch.get("complexity_label"),
        "shared_actuator_count": arch.get("shared_actuator_count"), "closed_loop_count": arch.get("closed_loop_count"),
        "critical_dependency_count": arch.get("critical_dependency_count"), "trend_state": temporal.get("trend_state"),
        "maintenance_debt_score": maintenance.get("score"), "flow_target_resolution_rate": conf.get("target_resolution_rate"),
        "automation_coverage_ratio": coverage.get("coverage_ratio"),
    }


def build_quality_gates(report):
    old = report.get("quality_gates") or {}
    replaced = {"consistency", "snapshot_consistency", "summary_consistency", "flow_confidence", "call_graph", "condition_semantics"}
    gates = [x for x in old.get("gates") or [] if str(x.get("key") or "") not in replaced]
    consistency = report.get("scan_consistency") or {}
    ok = bool(consistency.get("inventory_matches_entity_health"))
    gates.append(v080._gate("snapshot_consistency", "Cohérence du snapshot d'états", "pass" if ok else "fail", "Inventaire et santé des entités synchronisés" if ok else "Les compteurs d'états divergent"))
    plan, summary = report.get("action_plan") or {}, report.get("diagnostic_summary") or {}
    arch, executive = report.get("architecture_analysis") or {}, report.get("executive_summary") or {}
    sync = ((plan.get("counts") or {}).get("action_now") == (summary.get("priority_counts") or {}).get("action_now")
            and executive.get("shared_actuator_count") == arch.get("shared_actuator_count")
            and executive.get("closed_loop_count") == arch.get("closed_loop_count"))
    gates.append(v080._gate("summary_consistency", "Cohérence des résumés", "pass" if sync else "fail", "Résumé, plan et architecture synchronisés" if sync else "Un compteur résumé diverge de sa source"))
    conf = report.get("flow_confidence") or {}
    gates.append(v080._gate("flow_confidence", "Confiance des flux dynamiques", "pass" if conf.get("unresolved_dynamic_targets", 0) == 0 else "warning", f"{conf.get('low_confidence_dynamic_edges',0)} arête(s) à confiance réduite · {conf.get('unresolved_dynamic_targets',0)} non résolue(s)"))
    calls = report.get("call_graph_analysis") or {}
    gates.append(v080._gate("call_graph", "Graphe d'appels transitif", "warning" if calls.get("recursion_cycle_count", 0) else "pass", f"{calls.get('script_nodes',0)} script(s) · {calls.get('recursion_cycle_count',0)} cycle(s)"))
    sem = report.get("condition_semantics") or {}
    gates.append(v080._gate("condition_semantics", "Exclusivité des contrôleurs", "warning" if sem.get("parse_errors") else "pass", f"{sem.get('proven_exclusive_pair_count',0)} paire(s) démontrée(s) · {sem.get('unproven_pair_count',0)} restante(s)"))
    counts = Counter(str(x.get("status") or "warning") for x in gates)
    overall = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")
    report["quality_gates"] = {"model": "quality_gates_v2.1", "overall": overall, "counts": dict(counts), "gates": gates}
    return report["quality_gates"]


def _patch_history(report, history_path):
    history = load_history(history_path)
    if not history or str(history[-1].get("generated_at") or "") != str(report.get("generated_at") or ""):
        return
    item = dict(history[-1])
    item["report_version"] = VERSION
    item["flow_confidence"] = {
        "low_confidence_dynamic_edges": (report.get("flow_confidence") or {}).get("low_confidence_dynamic_edges"),
        "unresolved_dynamic_targets": (report.get("flow_confidence") or {}).get("unresolved_dynamic_targets"),
    }
    item["condition_semantics"] = {"proven_exclusive_pair_count": (report.get("condition_semantics") or {}).get("proven_exclusive_pair_count")}
    item["resilience"] = {"review_count": (report.get("resilience_analysis") or {}).get("review_count")}
    history[-1] = item
    save_history(history, history_path)


def enrich_v081(report, states_snapshot=None, history_path="/data/ha-doctor-history.json"):
    synchronize_state_snapshot(report, states_snapshot)
    build_flow_confidence(report)
    build_condition_semantics(report)
    build_transitive_call_graph(report)
    calibrate_operational_context(report, states_snapshot)
    build_resilience_analysis(report, states_snapshot)
    sync_action_counts(report)
    rebuild_executive_summary(report)
    build_quality_gates(report)
    report.setdefault("score_meta", {}).update({
        "model": "root_cause_temporal_v4_flow_v3_hardened", "hardening_version": VERSION,
        "state_snapshot_model": "single_state_snapshot_v1", "condition_semantics_model": "condition_semantics_v1",
        "call_graph_model": "transitive_call_graph_v1", "resilience_model": "resilience_spof_v1",
        "contextual_scoring_applied": False, "contextual_priority_calibration": True,
        "note": "0.8.1 conserve l'échelle V4 mais durcit cohérence, confiance, contexte, exclusivité, appels transitifs et résilience.",
    })
    old_caps = (report.get("report_schema") or {}).get("capabilities", [])
    report["report_schema"] = {
        "version": REPORT_SCHEMA_VERSION, "backward_compatible_with": ["0.5", "0.6", "0.7", "0.8"],
        "capabilities": list(dict.fromkeys(old_caps + ["single_state_snapshot", "flow_confidence_bands", "condition_semantics_v1", "transitive_script_scene_call_graph", "operational_context_calibration", "resilience_spof_v1", "quality_gates_v2_1"])),
    }
    report.setdefault("diagnostic_engine", {}).update({
        "version": "explain_v4_entity_flow_hardened", "single_state_snapshot": True,
        "flow_confidence_analysis": True, "condition_semantics": True, "transitive_call_graph": True,
        "operational_context_analysis": True, "resilience_analysis": True,
    })
    report.setdefault("privacy", {}).update({
        "automatic_configuration_changes": False, "state_snapshot_persisted": False,
        "condition_semantics_raw_yaml_persisted": False, "call_graph_raw_yaml_persisted": False,
        "resilience_raw_yaml_persisted": False,
    })
    report["version"] = VERSION
    _patch_history(report, history_path)
    return report
