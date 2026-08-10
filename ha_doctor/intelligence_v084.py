"""HA Doctor 0.8.4 semantic-lineage orchestrator."""
from collections import Counter

import intelligence_v083 as previous
import resilience_v083
from consistency_v084 import validate_report_consistency_v4
from lineage_v084 import BLAST_MODEL, LINEAGE_MODEL, apply_registry_lineage_blast_radius_v4, build_entity_lineage_v1
from resilience_v084 import build_resilience_recommendations_v1
from semantics_v084 import ARCH_MODEL, CONDITION_MODEL, FLOW_MODEL, build_condition_semantics_v4, normalize_flow_metadata_v31, recompute_architecture_post_flow
from temporal_v084 import MODEL as TEMPORAL_MODEL, apply_temporal_v31
from temporal_v060 import load_history, save_history

VERSION = "0.8.4"
REPORT_SCHEMA_VERSION = "ha-doctor-report/0.8.4"


def _gate(key, label, status, detail):
    return {"key": key, "label": label, "status": status, "detail": detail}


def build_quality_gates_v4(report):
    old = report.get("quality_gates") or {}
    replaced = {"flow_confidence", "condition_semantics", "resilience", "internal_consistency", "lineage", "temporal_semantics"}
    gates = [item for item in old.get("gates") or [] if str(item.get("key") or "") not in replaced]

    flow = report.get("flow_confidence") or {}
    gates.append(_gate(
        "flow_confidence", "Confiance des flux dynamiques", str(flow.get("quality_status") or "warning"),
        f"{float(flow.get('review_required_ratio',0))*100:.1f}% à revoir · {flow.get('literal_confirmed_promotions',0)} cible(s) confirmée(s) · {flow.get('unresolved_dynamic_targets',0)} non résolue(s)",
    ))

    lineage = report.get("entity_lineage") or {}
    lineage_status = "warning" if int(lineage.get("parse_error_count", 0) or 0) else "pass"
    gates.append(_gate(
        "lineage", "Lignée des entités", lineage_status,
        f"{lineage.get('confirmed_edge_count',0)} relation(s) confirmée(s) · {lineage.get('derived_entity_count',0)} entité(s) dérivée(s) · {lineage.get('parse_error_count',0)} erreur(s) de lecture",
    ))

    sem = report.get("condition_semantics") or {}
    sem_status = "warning" if (
        int(sem.get("physical_unproven_pair_count", 0) or 0) > 0
        or int(sem.get("contradictory_deterministic_pair_count", 0) or 0) > 0
        or sem.get("parse_errors")
    ) else "pass"
    gates.append(_gate(
        "condition_semantics", "Coordination des contrôleurs", sem_status,
        f"{sem.get('resolved_pair_count',0)} résolue(s) · {sem.get('protocol_coordinated_pair_count',0)} handoff(s) · {sem.get('physical_unproven_pair_count',0)} physique(s) à revoir",
    ))

    temporal = report.get("temporal_analysis") or {}
    gates.append(_gate(
        "temporal_semantics", "Sémantique temporelle", "pass",
        f"{temporal.get('resolved_since_previous_count',0)} réellement résolu(s) · {temporal.get('deescalated_since_previous_count',0)} déclassé(s) · {temporal.get('all_diagnostic_count',0)} diagnostic(s) suivis",
    ))

    resilience = report.get("resilience_analysis") or {}
    rec = report.get("resilience_recommendations") or {}
    res_status = "warning" if (
        int(resilience.get("review_count", 0) or 0) > 0
        or int(resilience.get("partial_count", 0) or 0) > 0
    ) else "pass"
    gates.append(_gate(
        "resilience", "Résilience des dépendances externes", res_status,
        f"{resilience.get('protected_count',0)} protégée(s) · {resilience.get('partial_count',0)} partielle(s) · {rec.get('count',0)} recommandation(s) priorisée(s)",
    ))

    consistency = report.get("consistency_analysis") or {}
    gates.append(_gate(
        "internal_consistency", "Cohérence interne du rapport", consistency.get("status", "warning"),
        f"{consistency.get('failure_count',0)} échec(s) · {consistency.get('warning_count',0)} avertissement(s)",
    ))

    counts = Counter(str(item.get("status") or "warning") for item in gates)
    overall = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")
    report["quality_gates"] = {"model": "quality_gates_v4", "overall": overall, "counts": dict(counts), "gates": gates}
    return report["quality_gates"]


def rebuild_executive_summary_v4(report):
    previous.rebuild_executive_summary_v3(report)
    executive = report.get("executive_summary") or {}
    primary = int((report.get("scores") or {}).get("global", 0) or 0)
    label = "Bon" if primary >= 85 else ("À surveiller" if primary >= 70 else "À corriger")
    counts = (report.get("action_plan") or {}).get("counts") or {}
    temporal = report.get("temporal_analysis") or {}
    lineage = report.get("entity_lineage") or {}
    sem = report.get("condition_semantics") or {}
    resilience = report.get("resilience_recommendations") or {}
    root = report.get("root_cause_summary") or {}
    v5 = report.get("score_v5_preview") or {}

    executive.update({
        "health_score": primary,
        "health_label": label,
        "entity_lineage_model": LINEAGE_MODEL,
        "entity_lineage_confirmed_edges": lineage.get("confirmed_edge_count", 0),
        "protocol_handoff_count": sem.get("protocol_coordinated_pair_count", 0),
        "resilience_recommendation_count": resilience.get("count", 0),
        "deescalated_since_previous_count": temporal.get("deescalated_since_previous_count", 0),
        "registry_lineage_incident_count": root.get("registry_lineage_incident_count", 0),
        "registry_impacted_automation_count": root.get("registry_impacted_automation_count", 0),
        "text": (
            f"Indice de santé V4 {primary}/100 ({label}). Preview V5 {v5.get('v5_preview_score', primary)}/100, non appliqué à l'historique. "
            f"{counts.get('action_now',0)} correction(s) prioritaire(s), {counts.get('verify',0)} vérification(s), {counts.get('optimize',0)} optimisation(s). "
            f"Temporal V3.1 : {temporal.get('persistent_count',0)} persistant(s), {temporal.get('deescalated_since_previous_count',0)} déclassé(s), {temporal.get('resolved_since_previous_count',0)} réellement résolu(s). "
            f"Lineage : {lineage.get('confirmed_edge_count',0)} relation(s) confirmée(s), {root.get('registry_impacted_automation_count',0)} automatisation(s) indirectement/directement corrélée(s). "
            f"Contrôleurs : {sem.get('protocol_coordinated_pair_count',0)} handoff(s) reconnu(s), {sem.get('physical_unproven_pair_count',0)} paire(s) physique(s) encore à revoir. "
            f"Résilience : {resilience.get('count',0)} dépendance(s) critique(s) transformée(s) en recommandation."
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
        "temporal_model": TEMPORAL_MODEL,
        "registry_blast_radius_model": BLAST_MODEL,
        "entity_lineage_model": LINEAGE_MODEL,
        "lineage_confirmed_edges": (report.get("entity_lineage") or {}).get("confirmed_edge_count", 0),
        "protocol_handoff_count": (report.get("condition_semantics") or {}).get("protocol_coordinated_pair_count", 0),
        "resilience_recommendation_count": (report.get("resilience_recommendations") or {}).get("count", 0),
    })
    history[-1] = snap
    save_history(history, history_path)


def enrich_v084(report, history_path="/data/ha-doctor-history.json"):
    normalize_flow_metadata_v31(report)
    recompute_architecture_post_flow(report)
    build_condition_semantics_v4(report)
    resilience_v083.build_resilience_analysis_v3(report)
    build_entity_lineage_v1(report)
    apply_registry_lineage_blast_radius_v4(report)
    build_resilience_recommendations_v1(report)
    apply_temporal_v31(report, history_path=history_path)
    previous.build_score_v5_preview(report)

    report["version"] = VERSION
    previous_capabilities = list((report.get("report_schema") or {}).get("capabilities") or [])
    report["report_schema"] = {
        "version": REPORT_SCHEMA_VERSION,
        "backward_compatible_with": ["0.5", "0.6", "0.7", "0.8", "0.8.1", "0.8.2", "0.8.3"],
        "capabilities": list(dict.fromkeys(previous_capabilities + [
            "flow_metadata_synchronization_v31",
            "architecture_post_flow_recompute_v3",
            "controller_phase_handoff_detection_v1",
            "entity_lineage_v1",
            "indirect_registry_blast_radius_v4",
            "temporal_v31_plan_and_diagnostics",
            "deescalation_vs_resolution_semantics",
            "resilience_action_recommendations_v1",
            "consistency_gates_v4",
            "quality_gates_v4",
        ])),
    }
    report.setdefault("score_meta", {}).update({
        "hardening_version": VERSION,
        "flow_confidence_model": FLOW_MODEL,
        "architecture_model": ARCH_MODEL,
        "condition_semantics_model": CONDITION_MODEL,
        "entity_lineage_model": LINEAGE_MODEL,
        "registry_blast_radius_model": BLAST_MODEL,
        "temporal_model": TEMPORAL_MODEL,
        "resilience_recommendation_model": "resilience_recommendations_v1",
        "quality_gate_model": "quality_gates_v4",
        "score_v5_applied": False,
        "note": (
            "0.8.4 synchronise les métriques Flow, recalcule l'architecture après promotion de confiance, distingue résolution/déclassement temporel, détecte les handoffs de contrôleurs et ajoute un lineage d'entités."
        ),
    })
    report.setdefault("diagnostic_engine", {}).update({
        "version": "explain_v6_semantic_lineage",
        "flow_metadata_v31": True,
        "architecture_post_flow_v3": True,
        "controller_protocols_v1": True,
        "entity_lineage_v1": True,
        "registry_blast_radius_v4": True,
        "temporal_v31": True,
        "resilience_recommendations_v1": True,
        "internal_consistency_v4": True,
    })
    report.setdefault("privacy", {}).update({
        "automatic_configuration_changes": False,
        "entity_lineage_raw_yaml_persisted": False,
        "entity_lineage_secret_values_persisted": False,
        "controller_protocol_raw_yaml_persisted": False,
        "registry_blast_radius_raw_states_persisted": False,
    })

    report.setdefault("root_cause_summary", {})["actionable_registry_incidents"] = sum(
        1 for item in (report.get("action_plan") or {}).get("items") or []
        if str(item.get("source_type") or "").startswith("registry_")
    )

    validate_report_consistency_v4(report)
    build_quality_gates_v4(report)
    rebuild_executive_summary_v4(report)
    _patch_history(report, history_path)
    return report
