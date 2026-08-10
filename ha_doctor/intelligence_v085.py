"""HA Doctor 0.8.5 branch-aware semantic hardening orchestrator."""
from collections import Counter

import intelligence_v082 as score_calibration
import intelligence_v084 as previous
from consistency_v085 import validate_report_consistency_v5
from semantics_v085 import CONDITION_MODEL, build_condition_semantics_v5
from temporal_v060 import load_history, save_history

VERSION = "0.8.5"
REPORT_SCHEMA_VERSION = "ha-doctor-report/0.8.5"
SCORE_MODEL = "score_v5_preview_v2_usage_aware"


def _usage_factor(explanation):
    """Modest non-destructive calibration for registry incidents with no HA use.

    Offline hardware still matters even when no automation references it, so the
    factor deliberately never collapses a real incident to zero.
    """
    source_type = str(explanation.get("source_type") or "")
    if not source_type.startswith("registry_"):
        return 1.0, "not_registry"
    impact = explanation.get("dependency_impact") or {}
    impacted = int(impact.get("impacted_automation_count", 0) or 0)
    if impacted > 0:
        return 1.0, "used_by_automation"
    if source_type == "registry_integration":
        return 0.95, "registry_integration_without_automation_dependency"
    if source_type in {"registry_device", "registry_cluster"}:
        return 0.90, "registry_device_without_automation_dependency"
    return 0.95, "registry_incident_without_automation_dependency"


def build_score_v5_preview_v2(report):
    primary = float((report.get("scores") or {}).get("global", 0) or 0)
    breakdown = list((report.get("score_meta") or {}).get("penalty_breakdown") or [])
    explanations = {
        str(item.get("id") or ""): item
        for item in report.get("diagnostic_explanations") or []
    }

    adjusted = []
    total = 0.0
    for item in breakdown:
        diagnostic_id = str(item.get("id") or "")
        try:
            technical_penalty = float(item.get("penalty", 0) or 0)
        except Exception:
            technical_penalty = 0.0
        explanation = explanations.get(diagnostic_id) or {}
        temporal = explanation.get("temporal") or {}
        context_factor = score_calibration._context_factor_for_id(report, diagnostic_id)
        try:
            persistence_factor = float(temporal.get("persistence_factor", 1.0) or 1.0)
        except Exception:
            persistence_factor = 1.0
        usage_factor, usage_reason = _usage_factor(explanation)

        impact = explanation.get("dependency_impact") or {}
        blast_level = str(impact.get("level") or "none")
        blast_factor = {
            "none": 1.0, "low": 1.0, "medium": 1.03,
            "high": 1.07, "critical": 1.10,
        }.get(blast_level, 1.0)
        if not str(explanation.get("source_type") or "").startswith("registry_"):
            blast_factor = 1.0

        contextual_penalty = technical_penalty * context_factor * persistence_factor * usage_factor * blast_factor
        total += contextual_penalty
        adjusted.append({
            "id": diagnostic_id,
            "title": item.get("title") or explanation.get("title"),
            "technical_penalty": round(technical_penalty, 2),
            "v5_penalty": round(contextual_penalty, 2),
            "context_factor": round(context_factor, 3),
            "persistence_factor": round(persistence_factor, 3),
            "usage_factor": round(usage_factor, 3),
            "usage_reason": usage_reason,
            "blast_radius": blast_level,
            "impacted_automation_count": int(impact.get("impacted_automation_count", 0) or 0),
        })

    technical_total = float((report.get("score_meta") or {}).get("penalty_total", 100.0 - primary) or 0)
    baseline = primary + technical_total
    raw = max(0.0, min(100.0, baseline - total))
    score = int(round(raw))
    adjusted.sort(key=lambda item: (-item["v5_penalty"], str(item.get("title") or "")))

    top3_gain = round(sum(item["v5_penalty"] for item in adjusted[:3]), 2)
    projected_raw = min(100.0, raw + top3_gain)
    scenarios = []
    running = raw
    for index, item in enumerate(adjusted[:5], start=1):
        running = min(100.0, running + item["v5_penalty"])
        scenarios.append({
            "rank": index,
            "id": item["id"],
            "title": item.get("title"),
            "estimated_gain": item["v5_penalty"],
            "projected_score_after_fix": int(round(running)),
        })

    result = {
        "model": SCORE_MODEL,
        "technical_v4_score": int(round(primary)),
        "v5_preview_score": score,
        "v5_preview_score_raw": round(raw, 2),
        "delta_vs_v4": round(raw - primary, 2),
        "technical_penalty_total": round(technical_total, 2),
        "v5_penalty_total": round(total, 2),
        "why_lost_points": adjusted[:12],
        "top_3_fix_estimated_gain": top3_gain,
        "projected_after_top_3_fixes": int(round(projected_raw)),
        "fix_scenarios": scenarios,
        "applied_to_primary_score": False,
        "usage_aware": True,
        "note": (
            "Preview uniquement : V2 ajoute un facteur d'usage modéré aux incidents registry sans dépendance "
            "d'automatisation. Un appareil réellement hors ligne conserve toujours une pénalité technique."
        ),
    }
    report["score_v5_preview"] = result
    return result


def _sync_controller_diagnostic(report):
    explanation = next(
        (item for item in report.get("diagnostic_explanations") or [] if str(item.get("source_id") or "") == "HD-AUTO-003"),
        None,
    )
    if not explanation:
        return
    for collection_name in ("action_plan", "recommendation_queue"):
        collection = report.get(collection_name) or {}
        for item in collection.get("items") or []:
            if str(item.get("id") or "") != str(explanation.get("id") or ""):
                continue
            for key in ("diagnosis", "impact", "why_now", "evidence", "first_check"):
                if key in explanation:
                    item[key] = explanation[key]


def _sync_counts(report):
    items = (report.get("action_plan") or {}).get("items") or []
    counts = Counter(str(item.get("priority") or "info") for item in items)
    plan = report.setdefault("action_plan", {})
    plan.update({
        "total": len(items), "displayed": len(items), "remaining": 0,
        "counts": {key: counts.get(key, 0) for key in ("action_now", "verify", "optimize")},
        "model": "correlated_action_plan_v3.2_branch_aware",
    })
    queue = report.setdefault("recommendation_queue", {})
    queue["items"] = list(items)
    queue["total"] = len(items)
    summary = report.setdefault("diagnostic_summary", {})
    summary["priority_counts"] = {
        key: counts.get(key, 0) for key in ("action_now", "verify", "optimize", "info")
    }
    summary["actionable_count"] = counts.get("action_now", 0) + counts.get("verify", 0)
    summary["source"] = "final_correlated_action_plan_v085"
    summary["plan_id_count"] = len(items)


def _quality_gates_v5(report):
    quality = previous.build_quality_gates_v4(report)
    quality["model"] = "quality_gates_v5_branch_aware"
    sem = report.get("condition_semantics") or {}
    for gate in quality.get("gates") or []:
        if str(gate.get("key") or "") == "condition_semantics":
            gate["detail"] = (
                f"{sem.get('resolved_pair_count',0)} résolue(s) · "
                f"{sem.get('branch_protocol_resolved_pair_count',0)} par branche · "
                f"{sem.get('physical_unproven_pair_count',0)} physique(s) à revoir"
            )
    quality["counts"] = dict(Counter(str(item.get("status") or "warning") for item in quality.get("gates") or []))
    quality["overall"] = "fail" if quality["counts"].get("fail") else ("warning" if quality["counts"].get("warning") else "pass")
    report["quality_gates"] = quality
    return quality


def _executive_summary_v5(report):
    executive = previous.rebuild_executive_summary_v4(report)
    sem = report.get("condition_semantics") or {}
    v5 = report.get("score_v5_preview") or {}
    primary = int((report.get("scores") or {}).get("global", 0) or 0)
    counts = (report.get("action_plan") or {}).get("counts") or {}
    temporal = report.get("temporal_analysis") or {}
    lineage = report.get("entity_lineage") or {}
    root = report.get("root_cause_summary") or {}
    resilience = report.get("resilience_recommendations") or {}
    executive.update({
        "branch_protocol_resolved_pair_count": sem.get("branch_protocol_resolved_pair_count", 0),
        "condition_semantics_model": CONDITION_MODEL,
        "score_v5_model": SCORE_MODEL,
        "score_v5_preview": v5.get("v5_preview_score", primary),
        "projected_after_top_3_fixes": v5.get("projected_after_top_3_fixes", primary),
        "text": (
            f"Indice de santé V4 {primary}/100 ({executive.get('health_label','—')}). "
            f"Preview V5 {v5.get('v5_preview_score', primary)}/100, non appliqué à l'historique. "
            f"{counts.get('action_now',0)} correction(s) prioritaire(s), {counts.get('verify',0)} vérification(s), {counts.get('optimize',0)} optimisation(s). "
            f"Temporal V3.1 : {temporal.get('persistent_count',0)} persistant(s), {temporal.get('deescalated_since_previous_count',0)} déclassé(s), {temporal.get('resolved_since_previous_count',0)} réellement résolu(s). "
            f"Lineage : {lineage.get('confirmed_edge_count',0)} relation(s) confirmée(s), {root.get('registry_impacted_automation_count',0)} automatisation(s) corrélée(s). "
            f"Contrôleurs V5 : {sem.get('protocol_coordinated_pair_count',0)} handoff(s) reconnu(s), dont {sem.get('branch_protocol_resolved_pair_count',0)} par analyse de branche ; {sem.get('physical_unproven_pair_count',0)} paire(s) physique(s) restent à revoir. "
            f"Résilience : {resilience.get('count',0)} dépendance(s) critique(s) priorisée(s)."
        ),
    })
    report["executive_summary"] = executive
    return executive


def _patch_history(report, history_path):
    history = load_history(history_path)
    if not history or str(history[-1].get("generated_at") or "") != str(report.get("generated_at") or ""):
        return
    snap = dict(history[-1])
    snap.update({
        "report_version": VERSION,
        "condition_semantics_model": CONDITION_MODEL,
        "branch_protocol_resolved_pair_count": (report.get("condition_semantics") or {}).get("branch_protocol_resolved_pair_count", 0),
        "physical_unproven_pair_count": (report.get("condition_semantics") or {}).get("physical_unproven_pair_count", 0),
        "score_v5_model": SCORE_MODEL,
        "score_v5_preview": (report.get("score_v5_preview") or {}).get("v5_preview_score"),
    })
    history[-1] = snap
    save_history(history, history_path)


def enrich_v085(report, history_path="/data/ha-doctor-history.json"):
    # scanner_v084 already produced the complete, stable 0.8.4 report. 0.8.5 is
    # intentionally a narrow semantic overlay: no second state fetch and no
    # second temporal observation.
    build_condition_semantics_v5(report)
    _sync_controller_diagnostic(report)
    _sync_counts(report)
    build_score_v5_preview_v2(report)

    report["version"] = VERSION
    previous_capabilities = list((report.get("report_schema") or {}).get("capabilities") or [])
    report["report_schema"] = {
        "version": REPORT_SCHEMA_VERSION,
        "backward_compatible_with": ["0.5", "0.6", "0.7", "0.8", "0.8.1", "0.8.2", "0.8.3", "0.8.4"],
        "capabilities": list(dict.fromkeys(previous_capabilities + [
            "branch_aware_controller_semantics_v5",
            "helper_phase_path_proofs",
            "usage_aware_score_v5_preview_v2",
            "cross_section_consistency_v5",
            "stale_version_copy_elimination",
        ])),
    }
    report.setdefault("score_meta", {}).update({
        "hardening_version": VERSION,
        "condition_semantics_model": CONDITION_MODEL,
        "quality_gate_model": "quality_gates_v5_branch_aware",
        "score_v5_preview": True,
        "score_v5_model": SCORE_MODEL,
        "score_v5_applied": False,
        "note": (
            "0.8.5 suit les chemins d'action pour reconnaître les handoffs helper par branche, "
            "renforce la cohérence croisée du rapport et calibre le preview V5 selon l'usage réel."
        ),
    })
    report.setdefault("diagnostic_engine", {}).update({
        "version": "explain_v7_branch_aware",
        "branch_aware_controller_semantics_v5": True,
        "cross_section_consistency_v5": True,
        "usage_aware_score_v5_preview_v2": True,
    })
    report.setdefault("privacy", {}).update({
        "automatic_configuration_changes": False,
        "branch_semantics_raw_yaml_persisted": False,
        "score_v5_raw_states_persisted": False,
    })

    root = report.setdefault("root_cause_summary", {})
    root["note"] = (
        "Plan corrélé après contexte, temporalité, confiance des flux, lineage, résilience et sémantique de contrôleurs par branche."
    )

    # Build user-facing summary first, then verify that it exactly matches the
    # underlying architecture/semantics before publishing the report.
    _executive_summary_v5(report)
    validate_report_consistency_v5(report)
    _quality_gates_v5(report)
    _patch_history(report, history_path)
    return report
