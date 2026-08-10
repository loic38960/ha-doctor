"""HA Doctor 0.8.3 hardening orchestrator."""
from collections import Counter

import intelligence_v080 as v080
import intelligence_v081 as v081
import intelligence_v082 as base
from consistency_v083 import validate_report_consistency_v3
from impact_v083 import apply_registry_blast_radius_v3
from resilience_v083 import build_resilience_analysis_v3
from semantics_v083 import build_condition_semantics_v3, build_flow_confidence_v3
from temporal_v083 import apply_temporal_v3
from temporal_v060 import load_history, save_history

VERSION = "0.8.3"
REPORT_SCHEMA_VERSION = "ha-doctor-report/0.8.3"


def build_score_v5_preview(report):
    """Non-destructive score preview with explainable fix projections."""
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
        context_factor = base._context_factor_for_id(report, diagnostic_id)
        persistence_factor = float(temporal.get("persistence_factor", 1.0) or 1.0)

        # V4 already includes an older dependency multiplier. V5 preview only
        # adds a small registry-specific correction from the new blast radius.
        impact = explanation.get("dependency_impact") or {}
        blast_level = str(impact.get("level") or "none")
        blast_factor = {
            "none": 1.0, "low": 1.0, "medium": 1.03,
            "high": 1.07, "critical": 1.10,
        }.get(blast_level, 1.0)
        if not str(explanation.get("source_type") or "").startswith("registry_"):
            blast_factor = 1.0

        contextual_penalty = technical_penalty * context_factor * persistence_factor * blast_factor
        total += contextual_penalty
        adjusted.append({
            "id": diagnostic_id,
            "title": item.get("title") or explanation.get("title"),
            "technical_penalty": round(technical_penalty, 2),
            "v5_penalty": round(contextual_penalty, 2),
            "context_factor": round(context_factor, 3),
            "persistence_factor": round(persistence_factor, 3),
            "blast_radius": blast_level,
        })

    # Use the V4 implied baseline so the preview remains comparable even if
    # category caps or rounding were used upstream.
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
        "model": "score_v5_preview_v1",
        "technical_v4_score": int(round(primary)),
        "v5_preview_score": score,
        "v5_preview_score_raw": round(raw, 2),
        "delta_vs_v4": round(raw - primary, 2),
        "technical_penalty_total": round(technical_total, 2),
        "v5_penalty_total": round(total, 2),
        "why_lost_points": adjusted[:10],
        "top_3_fix_estimated_gain": top3_gain,
        "projected_after_top_3_fixes": int(round(projected_raw)),
        "fix_scenarios": scenarios,
        "applied_to_primary_score": False,
        "note": (
            "Preview de calibration : le Score V4 historique reste la référence tant que "
            "V5 n'a pas été validé sur plusieurs installations."
        ),
    }
    report["score_v5_preview"] = result
    return result


def _sync_plan(report):
    v081.sync_action_counts(report)
    report.setdefault("diagnostic_summary", {})["source"] = "final_correlated_action_plan_v083"
    report["diagnostic_summary"]["plan_id_count"] = len((report.get("action_plan") or {}).get("items") or [])


def build_quality_gates_v3(report):
    old = report.get("quality_gates") or {}
    replaced = {"flow_confidence", "condition_semantics", "resilience", "internal_consistency"}
    gates = [item for item in old.get("gates") or [] if str(item.get("key") or "") not in replaced]

    flow = report.get("flow_confidence") or {}
    gates.append(v080._gate(
        "flow_confidence", "Confiance des flux dynamiques",
        str(flow.get("quality_status") or "warning"),
        f"{float(flow.get('review_required_ratio',0))*100:.1f}% réellement à revoir · "
        f"{flow.get('literal_confirmed_promotions',0)} cible(s) littérale(s) confirmée(s) · "
        f"{flow.get('unresolved_dynamic_targets',0)} non résolue(s)",
    ))

    sem = report.get("condition_semantics") or {}
    sem_status = "warning" if (
        int(sem.get("physical_unproven_pair_count", 0) or 0) > 0
        or int(sem.get("contradictory_deterministic_pair_count", 0) or 0) > 0
        or sem.get("parse_errors")
    ) else "pass"
    gates.append(v080._gate(
        "condition_semantics", "Coordination des contrôleurs", sem_status,
        f"{sem.get('resolved_pair_count',0)} résolue(s) · "
        f"{sem.get('physical_unproven_pair_count',0)} physique(s) · "
        f"{sem.get('helper_unproven_pair_count',0)} helper(s)",
    ))

    resilience = report.get("resilience_analysis") or {}
    res_status = "warning" if (
        int(resilience.get("review_count", 0) or 0) > 0
        or int(resilience.get("partial_count", 0) or 0) > 0
    ) else "pass"
    gates.append(v080._gate(
        "resilience", "Résilience des dépendances externes", res_status,
        f"{resilience.get('protected_count',0)} protégée(s) · "
        f"{resilience.get('partial_count',0)} partielle(s) · "
        f"{resilience.get('review_count',0)} à revoir · "
        f"{resilience.get('configuration_dependency_count',0)} helper(s) séparé(s)",
    ))

    consistency = report.get("consistency_analysis") or {}
    gates.append(v080._gate(
        "internal_consistency", "Cohérence interne du rapport",
        consistency.get("status", "warning"),
        f"{consistency.get('failure_count',0)} échec(s) · {consistency.get('warning_count',0)} avertissement(s)",
    ))

    counts = Counter(str(item.get("status") or "warning") for item in gates)
    overall = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")
    report["quality_gates"] = {
        "model": "quality_gates_v3",
        "overall": overall,
        "counts": dict(counts),
        "gates": gates,
    }
    return report["quality_gates"]


def rebuild_executive_summary_v3(report):
    base.rebuild_executive_summary_v2(report)
    executive = report.get("executive_summary") or {}
    temporal = report.get("temporal_analysis") or {}
    flow = report.get("flow_confidence") or {}
    sem = report.get("condition_semantics") or {}
    resilience = report.get("resilience_analysis") or {}
    v5 = report.get("score_v5_preview") or {}
    root = report.get("root_cause_summary") or {}
    primary = int((report.get("scores") or {}).get("global", 0) or 0)
    label = "Bon" if primary >= 85 else ("À surveiller" if primary >= 70 else "À corriger")
    counts = (report.get("action_plan") or {}).get("counts") or {}

    executive.update({
        "health_score": primary,
        "health_label": label,
        "score_v5_preview": v5.get("v5_preview_score"),
        "projected_after_top_3_fixes": v5.get("projected_after_top_3_fixes"),
        "temporal_model": temporal.get("model"),
        "registry_blast_radius_model": root.get("registry_blast_radius_model"),
        "text": (
            f"Indice de santé V4 {primary}/100 ({label}). "
            f"Preview V5 {v5.get('v5_preview_score', primary)}/100, non appliqué à l'historique ; "
            f"les 3 premières corrections donneraient environ {v5.get('projected_after_top_3_fixes', primary)}/100. "
            f"{counts.get('action_now',0)} correction(s) prioritaire(s), "
            f"{counts.get('verify',0)} vérification(s), {counts.get('optimize',0)} optimisation(s). "
            f"Temporal V3 : {temporal.get('persistent_count',0)} persistant(s), "
            f"{temporal.get('new_count',0)} nouveau(x), rescans rapides neutralisés. "
            f"Flux V3 : {float(flow.get('review_required_ratio',0))*100:.1f}% réellement à revoir. "
            f"Contrôleurs : {sem.get('physical_unproven_pair_count',0)} paire(s) physique(s) non prouvée(s), "
            f"{sem.get('helper_unproven_pair_count',0)} helper(s). "
            f"Résilience externe : {resilience.get('protected_count',0)} protégée(s), "
            f"{resilience.get('partial_count',0)} partielle(s), {resilience.get('review_count',0)} à revoir."
        ),
    })
    report["executive_summary"] = executive
    return executive


def _patch_history(report, history_path):
    history = load_history(history_path)
    if not history or str(history[-1].get("generated_at") or "") != str(report.get("generated_at") or ""):
        return
    snap = dict(history[-1])
    snap["report_version"] = VERSION
    snap["score_v5_preview"] = (report.get("score_v5_preview") or {}).get("v5_preview_score")
    snap["temporal_model"] = (report.get("temporal_analysis") or {}).get("model")
    snap["registry_blast_radius_model"] = (report.get("root_cause_summary") or {}).get("registry_blast_radius_model")
    snap["flow_confidence"] = {
        "review_required_ratio": (report.get("flow_confidence") or {}).get("review_required_ratio"),
        "unresolved_dynamic_targets": (report.get("flow_confidence") or {}).get("unresolved_dynamic_targets"),
    }
    history[-1] = snap
    save_history(history, history_path)


def enrich_v083(report, history_path="/data/ha-doctor-history.json"):
    # 0.8.2 has already done the stable calibration. V3 layers are deliberately
    # non-destructive to the primary V4 score.
    apply_temporal_v3(report, history_path=history_path)
    apply_registry_blast_radius_v3(report)
    build_flow_confidence_v3(report)
    build_condition_semantics_v3(report)
    build_resilience_analysis_v3(report)
    _sync_plan(report)
    build_score_v5_preview(report)

    report["version"] = VERSION
    report["report_schema"] = {
        "version": REPORT_SCHEMA_VERSION,
        "backward_compatible_with": ["0.5", "0.6", "0.7", "0.8", "0.8.1", "0.8.2"],
        "capabilities": list(dict.fromkeys(
            ((report.get("report_schema") or {}).get("capabilities") or []) + [
                "temporal_v3_duration_qualified",
                "rapid_rescan_persistence_protection",
                "registry_blast_radius_v3",
                "flow_confidence_v3",
                "literal_dynamic_target_confirmation",
                "condition_semantics_v3",
                "physical_vs_helper_controller_risk",
                "deterministic_conflict_evidence",
                "resilience_spof_v3",
                "structured_state_guard_detection",
                "helper_spof_separation",
                "score_v5_preview_v1",
                "fix_score_projection",
                "internal_consistency_v3",
                "quality_gates_v3",
                "runtime_health_smoke_test",
            ]
        )),
    }
    report.setdefault("score_meta", {}).update({
        "hardening_version": VERSION,
        "temporal_model": "temporal_v3_duration_qualified",
        "registry_blast_radius_model": "registry_blast_radius_v3",
        "flow_confidence_model": "flow_confidence_v3",
        "condition_semantics_model": "condition_semantics_v3",
        "resilience_model": "resilience_spof_v3",
        "quality_gate_model": "quality_gates_v3",
        "score_v5_preview": True,
        "score_v5_applied": False,
        "note": (
            "0.8.3 durcit la persistance temporelle, le blast radius registry, la confiance "
            "des flux, les conflits physiques, la résilience et la cohérence interne. "
            "Le Score V5 reste un preview."
        ),
    })
    report.setdefault("diagnostic_engine", {}).update({
        "version": "explain_v5_hardening_preview",
        "temporal_v3": True,
        "registry_blast_radius_v3": True,
        "flow_confidence_v3": True,
        "condition_semantics_v3": True,
        "resilience_v3": True,
        "score_v5_preview": True,
        "internal_consistency_v3": True,
    })
    report.setdefault("privacy", {}).update({
        "automatic_configuration_changes": False,
        "temporal_history_raw_states_persisted": False,
        "registry_blast_radius_raw_states_persisted": False,
        "score_v5_raw_states_persisted": False,
        "consistency_engine_raw_states_persisted": False,
    })

    # Version must be final before the consistency check.
    consistency = validate_report_consistency_v3(report)
    build_quality_gates_v3(report)
    rebuild_executive_summary_v3(report)
    _patch_history(report, history_path)
    return report
