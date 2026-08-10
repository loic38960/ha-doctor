"""HA Doctor 0.8.2 calibration and final-consistency orchestrator."""

from collections import Counter

import intelligence_v080 as v080
import intelligence_v081 as v081
from temporal_v060 import load_history, save_history
from semantics_v082 import build_flow_confidence_v2, build_condition_semantics_v2
from resilience_v082 import build_resilience_analysis_v2

VERSION = "0.8.2"
REPORT_SCHEMA_VERSION = "ha-doctor-report/0.8.2"


def _drop_plan_ids(report, ids):
    ids = set(ids)
    for key in ("action_plan", "recommendation_queue"):
        section = report.get(key) or {}
        section["items"] = [item for item in section.get("items") or [] if item.get("id") not in ids]
        if "top" in section:
            section["top"] = [item for item in section.get("top") or [] if item.get("id") not in ids]


def calibrate_controller_action(report):
    sem = report.get("condition_semantics") or {}
    if int(sem.get("unproven_pair_count", 0) or 0) != 0:
        return

    target_id = "DX-HD-AUTO-003"
    for finding in report.get("findings") or []:
        if finding.get("rule_id") == "HD-AUTO-003":
            finding["priority"] = "info"
            finding["priority_label"] = "Informations"
            finding["summary"] = (
                "Toutes les paires de contrôleurs détectées ont été expliquées par une "
                "exclusivité ou une coordination statiquement démontrable."
            )
    for explanation in report.get("diagnostic_explanations") or []:
        if explanation.get("id") == target_id:
            explanation["priority"] = "info"
            explanation["priority_label"] = "Informations"
            explanation["why_now"] = "Aucune paire de contrôleurs contradictoire ne reste démontrée."
    _drop_plan_ids(report, {target_id})


def _context_factor_for_id(report, diagnostic_id):
    registry = report.get("registry_analysis") or {}
    integrations = ((registry.get("integration_health") or {}).get("groups") or [])
    devices = ((registry.get("device_health") or {}).get("groups") or [])

    if diagnostic_id.startswith("DX-REG-INT-"):
        name = diagnostic_id[len("DX-REG-INT-"):]
        for group in integrations:
            if str(group.get("integration") or "") == name and group.get("context_factor") is not None:
                try:
                    return max(0.0, min(1.0, float(group.get("context_factor"))))
                except Exception:
                    return 1.0

    if diagnostic_id.startswith("DX-REG-CLUSTER-"):
        name = diagnostic_id[len("DX-REG-CLUSTER-"):]
        factors = []
        for group in devices:
            platforms = {str(item) for item in group.get("platforms") or []}
            if name not in platforms or group.get("context_factor") is None:
                continue
            try:
                factors.append(max(0.0, min(1.0, float(group.get("context_factor")))))
            except Exception:
                pass
        if factors:
            return sum(factors) / len(factors)

    return 1.0


def build_contextual_score_preview(report):
    """Calculate a non-destructive contextual preview next to the stable V4 score."""
    technical = float((report.get("scores") or {}).get("global", 0) or 0)
    context = report.get("operational_context") or {}
    deescalated = set(context.get("diagnostics_deescalated") or [])
    breakdown = (report.get("score_meta") or {}).get("penalty_breakdown") or []
    relief = 0.0
    items = []

    for penalty in breakdown:
        diagnostic_id = str(penalty.get("id") or "")
        if diagnostic_id not in deescalated:
            continue
        try:
            value = float(penalty.get("penalty", 0) or 0)
        except Exception:
            value = 0.0
        factor = _context_factor_for_id(report, diagnostic_id)
        local_relief = value * (1.0 - factor)
        relief += local_relief
        items.append({
            "id": diagnostic_id,
            "technical_penalty": round(value, 2),
            "context_factor": round(factor, 3),
            "preview_relief": round(local_relief, 2),
        })

    raw = max(0.0, min(100.0, technical + relief))
    contextual = int(round(raw))
    label = "Bon" if contextual >= 85 else ("À surveiller" if contextual >= 70 else "À corriger")
    result = {
        "model": "contextual_score_preview_v1",
        "technical_score": int(round(technical)),
        "contextual_score": contextual,
        "contextual_score_raw": round(raw, 2),
        "delta": round(raw - technical, 2),
        "health_label": label,
        "penalty_relief": round(relief, 2),
        "deescalated_diagnostics": items,
        "applied_to_primary_score": False,
        "note": (
            "Preview uniquement : le Score V4 technique reste inchangé pour préserver "
            "la continuité de l'historique."
        ),
    }
    report["contextual_score_preview"] = result
    context["health_score_recomputed"] = False
    context["contextual_score_preview"] = contextual
    return result


def sync_final_consistency(report):
    """Make final plan, registry and temporal counters derive from final presentation state."""
    v081.sync_action_counts(report)
    plan_items = (report.get("action_plan") or {}).get("items") or []
    plan_ids = {str(item.get("id") or "") for item in plan_items}

    registry_items = [
        item for item in plan_items
        if str(item.get("source_type") or "").startswith("registry_")
    ]
    detected_registry = [
        item for item in report.get("diagnostic_explanations") or []
        if str(item.get("source_type") or "").startswith("registry_")
    ]

    root = report.setdefault("root_cause_summary", {})
    root.update({
        "actionable_registry_incidents": len(registry_items),
        "detected_registry_incidents": len(detected_registry),
        "integration_incidents": sum(1 for item in registry_items if item.get("source_type") == "registry_integration"),
        "device_incidents": sum(1 for item in registry_items if item.get("source_type") == "registry_device"),
        "cluster_incidents": sum(1 for item in registry_items if item.get("source_type") == "registry_cluster"),
        "transient_observations": len(report.get("registry_observations") or []),
    })

    temporal = report.get("temporal_analysis") or {}
    if temporal:
        new_ids = []
        persistent_ids = []
        for item in plan_items:
            status = str((item.get("temporal") or {}).get("status") or "")
            diagnostic_id = str(item.get("id") or "")
            if status == "new":
                new_ids.append(diagnostic_id)
            elif status == "persistent":
                persistent_ids.append(diagnostic_id)

        explanations = report.get("diagnostic_explanations") or []
        temporal.update({
            "scope": "final_action_plan",
            "new_count": len(new_ids),
            "persistent_count": len(persistent_ids),
            "new_ids": new_ids,
            "persistent_ids": persistent_ids,
            "new_action_now_count": sum(
                1 for item in plan_items
                if item.get("priority") == "action_now" and str((item.get("temporal") or {}).get("status") or "") == "new"
            ),
            "all_explanation_new_count": sum(
                1 for item in explanations if str((item.get("temporal") or {}).get("status") or "") == "new"
            ),
            "all_explanation_persistent_count": sum(
                1 for item in explanations if str((item.get("temporal") or {}).get("status") or "") == "persistent"
            ),
            "presentation_note": (
                "new_count/persistent_count décrivent uniquement le plan d'action final ; "
                "les diagnostics info ou supprimés du bruit restent comptés séparément."
            ),
        })

        regression = report.get("regression_analysis") or {}
        regression.update({
            "new_diagnostic_count": len(new_ids),
            "new_action_now_count": temporal.get("new_action_now_count", 0),
            "persistent_count": len(persistent_ids),
        })

    summary = report.setdefault("diagnostic_summary", {})
    summary["source"] = "final_correlated_action_plan_v082"
    summary["plan_id_count"] = len(plan_ids)
    return report


def rebuild_executive_summary_v2(report):
    v081.rebuild_executive_summary(report)
    executive = report.get("executive_summary") or {}
    score = int((report.get("scores") or {}).get("global", 0) or 0)
    counts = (report.get("action_plan") or {}).get("counts") or {}
    arch = report.get("architecture_analysis") or {}
    conf = report.get("flow_confidence") or {}
    coverage = report.get("automation_coverage") or {}
    sem = report.get("condition_semantics") or {}
    resilience = report.get("resilience_analysis") or {}
    maintenance = report.get("maintenance_debt") or {}
    preview = report.get("contextual_score_preview") or {}
    root = report.get("root_cause_summary") or {}
    label = "Bon" if score >= 85 else ("À surveiller" if score >= 70 else "À corriger")

    context_text = ""
    if int(preview.get("contextual_score", score) or score) != score:
        context_text = (
            f" Preview contextualisé {preview.get('contextual_score')}/100 "
            f"({preview.get('delta', 0):+g}), non appliqué à l'historique."
        )

    executive.update({
        "health_score": score,
        "health_label": label,
        "contextual_health_score_preview": preview.get("contextual_score"),
        "actionable_root_cause_count": root.get("actionable_registry_incidents", 0),
        "detected_root_cause_count": root.get("detected_registry_incidents", 0),
        "text": (
            f"Indice de santé V4 {score}/100 ({label}).{context_text} "
            f"{counts.get('action_now',0)} correction(s) prioritaire(s), "
            f"{counts.get('verify',0)} point(s) à vérifier et {counts.get('optimize',0)} optimisation(s). "
            f"Causes registry : {root.get('actionable_registry_incidents',0)} actionnable(s) sur "
            f"{root.get('detected_registry_incidents',0)} détectée(s). "
            f"Architecture : {arch.get('shared_actuator_count',0)} actionneur(s) partagé(s), "
            f"{arch.get('closed_loop_count',0)} boucle(s), {arch.get('critical_dependency_count',0)} dépendance(s) critique(s). "
            f"Contrôleurs : {sem.get('resolved_pair_count',0)} paire(s) résolue(s), "
            f"{sem.get('unproven_pair_count',0)} à vérifier. "
            f"Résilience : {resilience.get('protected_count',0)} protégée(s), "
            f"{resilience.get('partial_count',0)} partielle(s), {resilience.get('review_count',0)} à revoir. "
            f"Flux : {float(conf.get('target_resolution_rate',0))*100:.1f}% résolus, "
            f"{float(conf.get('low_confidence_ratio',0))*100:.1f}% dynamiques à confiance réduite ; "
            f"couverture {float(coverage.get('coverage_ratio',0))*100:.1f}%. "
            f"Dette maintenance : {maintenance.get('score',0)}/100 ({maintenance.get('label','n/a')})."
        ),
    })
    report["executive_summary"] = executive
    return executive


def build_quality_gates_v22(report):
    old = report.get("quality_gates") or {}
    replaced = {
        "snapshot_consistency", "summary_consistency", "flow_confidence",
        "condition_semantics", "resilience",
    }
    gates = [item for item in old.get("gates") or [] if str(item.get("key") or "") not in replaced]

    consistency = report.get("scan_consistency") or {}
    snapshot_ok = bool(consistency.get("inventory_matches_entity_health"))
    gates.append(v080._gate(
        "snapshot_consistency", "Cohérence du snapshot d'états",
        "pass" if snapshot_ok else "fail",
        "Inventaire et santé des entités synchronisés" if snapshot_ok else "Les compteurs d'états divergent",
    ))

    plan = report.get("action_plan") or {}
    summary = report.get("diagnostic_summary") or {}
    root = report.get("root_cause_summary") or {}
    plan_registry_count = sum(
        1 for item in plan.get("items") or []
        if str(item.get("source_type") or "").startswith("registry_")
    )
    sync = (
        (plan.get("counts") or {}).get("action_now") == (summary.get("priority_counts") or {}).get("action_now")
        and int(root.get("actionable_registry_incidents", 0) or 0) == plan_registry_count
    )
    gates.append(v080._gate(
        "summary_consistency", "Cohérence des résumés",
        "pass" if sync else "fail",
        "Plan, résumé et causes actionnables synchronisés" if sync else "Un compteur final diverge de sa source",
    ))

    conf = report.get("flow_confidence") or {}
    flow_status = str(conf.get("quality_status") or "warning")
    gates.append(v080._gate(
        "flow_confidence", "Confiance des flux dynamiques", flow_status,
        f"{float(conf.get('low_confidence_ratio',0))*100:.1f}% à confiance réduite · "
        f"{conf.get('unresolved_dynamic_targets',0)} non résolue(s)",
    ))

    sem = report.get("condition_semantics") or {}
    if sem.get("parse_errors"):
        sem_status = "warning"
    elif int(sem.get("unproven_pair_count", 0) or 0) > 0:
        sem_status = "warning"
    else:
        sem_status = "pass"
    gates.append(v080._gate(
        "condition_semantics", "Coordination des contrôleurs", sem_status,
        f"{sem.get('resolved_pair_count',0)} paire(s) résolue(s) · {sem.get('unproven_pair_count',0)} restante(s)",
    ))

    resilience = report.get("resilience_analysis") or {}
    res_status = "warning" if (
        int(resilience.get("review_count", 0) or 0) > 0
        or int(resilience.get("partial_count", 0) or 0) > 0
    ) else "pass"
    gates.append(v080._gate(
        "resilience", "Résilience des dépendances critiques", res_status,
        f"{resilience.get('protected_count',0)} protégée(s) · "
        f"{resilience.get('partial_count',0)} partielle(s) · {resilience.get('review_count',0)} à revoir",
    ))

    counts = Counter(str(item.get("status") or "warning") for item in gates)
    overall = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")
    report["quality_gates"] = {
        "model": "quality_gates_v2.2",
        "overall": overall,
        "counts": dict(counts),
        "gates": gates,
    }
    return report["quality_gates"]


def _patch_history(report, history_path):
    history = load_history(history_path)
    if not history or str(history[-1].get("generated_at") or "") != str(report.get("generated_at") or ""):
        return
    item = dict(history[-1])
    item["report_version"] = VERSION
    item["flow_confidence"] = {
        "low_confidence_ratio": (report.get("flow_confidence") or {}).get("low_confidence_ratio"),
        "unresolved_dynamic_targets": (report.get("flow_confidence") or {}).get("unresolved_dynamic_targets"),
    }
    item["condition_semantics"] = {
        "resolved_pair_count": (report.get("condition_semantics") or {}).get("resolved_pair_count"),
        "unproven_pair_count": (report.get("condition_semantics") or {}).get("unproven_pair_count"),
    }
    item["resilience"] = {
        "protected_count": (report.get("resilience_analysis") or {}).get("protected_count"),
        "partial_count": (report.get("resilience_analysis") or {}).get("partial_count"),
        "review_count": (report.get("resilience_analysis") or {}).get("review_count"),
    }
    item["contextual_score_preview"] = (report.get("contextual_score_preview") or {}).get("contextual_score")
    history[-1] = item
    save_history(history, history_path)


def enrich_v082(report, history_path="/data/ha-doctor-history.json"):
    build_flow_confidence_v2(report)
    build_condition_semantics_v2(report)
    calibrate_controller_action(report)
    build_resilience_analysis_v2(report)
    build_contextual_score_preview(report)
    sync_final_consistency(report)
    rebuild_executive_summary_v2(report)
    build_quality_gates_v22(report)

    report.setdefault("score_meta", {}).update({
        "hardening_version": VERSION,
        "condition_semantics_model": "condition_semantics_v2",
        "resilience_model": "resilience_spof_v2",
        "quality_gate_model": "quality_gates_v2.2",
        "contextual_scoring_applied": False,
        "contextual_score_preview": True,
        "note": (
            "0.8.2 conserve le Score V4 technique et ajoute un preview contextualisé, "
            "des gates plus stricts, Condition Semantics V2 et Resilience V2."
        ),
    })

    old_caps = (report.get("report_schema") or {}).get("capabilities", [])
    report["report_schema"] = {
        "version": REPORT_SCHEMA_VERSION,
        "backward_compatible_with": ["0.5", "0.6", "0.7", "0.8", "0.8.1"],
        "capabilities": list(dict.fromkeys(old_caps + [
            "flow_confidence_quality_ratio",
            "condition_semantics_v2",
            "startup_reconciliation_detection",
            "deterministic_command_coordination",
            "resilience_spof_v2",
            "contextual_score_preview_v1",
            "final_counter_consistency_v2",
            "quality_gates_v2_2",
        ])),
    }
    report.setdefault("diagnostic_engine", {}).update({
        "version": "explain_v4_entity_flow_calibrated",
        "condition_semantics": True,
        "condition_semantics_v2": True,
        "resilience_analysis": True,
        "resilience_v2": True,
        "contextual_score_preview": True,
        "final_consistency_pass": True,
    })
    report.setdefault("privacy", {}).update({
        "automatic_configuration_changes": False,
        "condition_semantics_raw_yaml_persisted": False,
        "resilience_raw_yaml_persisted": False,
        "contextual_score_raw_states_persisted": False,
    })

    report["version"] = VERSION
    _patch_history(report, history_path)
    return report
