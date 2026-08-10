"""HA Doctor 0.8.8 semantic/control-intelligence orchestrator.

0.8.8 is a read-only calibration layer over the validated 0.8.7 report. It
refines controller arbitration and resilience roles without changing the V4
primary health score or performing additional Home Assistant state reads.
"""
from collections import Counter

import hardening_v087 as v087
import resilience_v084 as recommendation_sync
from resilience_v088 import (
    MODEL as RESILIENCE_MODEL,
    RECOMMENDATION_MODEL,
    build_resilience_analysis_v4,
    build_resilience_recommendations_v2,
)
from semantics_v088 import CONDITION_MODEL, refine_condition_semantics_v6
from temporal_v060 import load_history, save_history

VERSION = "0.8.8"
REPORT_SCHEMA = "ha-doctor-report/0.8.8"
QUALITY_MODEL = "quality_gates_v6_role_aware"
CONSISTENCY_MODEL = "consistency_gates_v6_semantic_roles"


def _priority_counts(items):
    counts = Counter(str(item.get("priority") or "info") for item in items if isinstance(item, dict))
    return {key: counts.get(key, 0) for key in ("action_now", "verify", "optimize", "info")}


def _sync_action_sections(report):
    # Reuse the stable ordering/counter synchronizer after the resilience
    # recommendation has potentially been removed or rebuilt.
    recommendation_sync._sync_sections(report)
    plan = report.setdefault("action_plan", {})
    plan["model"] = "correlated_action_plan_v3.3_control_aware"
    items = plan.get("items") or []
    counts = _priority_counts(items)
    summary = report.setdefault("diagnostic_summary", {})
    summary["source"] = "final_correlated_action_plan_v088"
    summary["priority_counts"] = counts
    summary["actionable_count"] = counts["action_now"] + counts["verify"]
    summary["plan_id_count"] = len(items)
    summary["headline"] = (
        f"{counts['action_now']} correction(s) prioritaire(s), "
        f"{counts['verify']} point(s) à vérifier et {counts['optimize']} optimisation(s)."
    )


def _sync_architecture(report):
    sem = report.get("condition_semantics") or {}
    architecture = report.setdefault("architecture_analysis", {})
    architecture.update({
        "condition_semantics_model": CONDITION_MODEL,
        "physical_unproven_controller_pair_count": int(sem.get("physical_unproven_pair_count", 0) or 0),
        "helper_unproven_controller_pair_count": int(sem.get("helper_unproven_pair_count", 0) or 0),
        "branch_protocol_resolved_pair_count": int(sem.get("branch_protocol_resolved_pair_count", 0) or 0),
        "semantic_v6_resolved_pair_count": int(sem.get("semantic_v6_resolved_pair_count", 0) or 0),
        "supervisory_interlock_pair_count": int(sem.get("supervisory_interlock_pair_count", 0) or 0),
        "mediated_interlock_pair_count": int(sem.get("mediated_interlock_pair_count", 0) or 0),
        "membership_exclusive_pair_count": int(sem.get("membership_exclusive_pair_count", 0) or 0),
    })


def _sync_controller_summary(report):
    # Build the proven 0.8.7 entity/pair identity from the final V6 pair list.
    report = v087.harden_report_v087(report)
    sem = report.get("condition_semantics") or {}
    summary = report.setdefault("controller_review_summary", {})
    summary.update({
        "model": "controller_review_summary_v2_semantic_v6",
        "semantic_v6_resolved_pair_count": int(sem.get("semantic_v6_resolved_pair_count", 0) or 0),
        "membership_exclusive_pair_count": int(sem.get("membership_exclusive_pair_count", 0) or 0),
        "supervisory_interlock_pair_count": int(sem.get("supervisory_interlock_pair_count", 0) or 0),
        "mediated_interlock_pair_count": int(sem.get("mediated_interlock_pair_count", 0) or 0),
    })

    physical = int(summary.get("physical_pair_count", 0) or 0)
    helper = int(summary.get("helper_pair_count", 0) or 0)
    entity_count = int(summary.get("entity_count", 0) or 0)
    pair_count = int(summary.get("pair_count", 0) or 0)
    v6 = int(summary.get("semantic_v6_resolved_pair_count", 0) or 0)

    finding = next((x for x in report.get("findings") or [] if x.get("rule_id") == "HD-AUTO-003"), None)
    if finding:
        finding["summary"] = (
            f"{physical} paire(s) sur actionneur physique restent à vérifier, "
            f"{helper} paire(s) concernent seulement des helpers ; "
            f"{v6} paire(s) supplémentaires ont été expliquées par la sémantique V6."
        )
        finding["controller_review_summary"] = dict(summary)

    for item in (report.get("action_plan") or {}).get("items") or []:
        if not isinstance(item, dict) or item.get("source_id") != "HD-AUTO-003":
            continue
        item["diagnosis"] = (
            f"{pair_count} paire(s) sur {entity_count} entité(s) restent non prouvées, "
            f"dont {physical} paire(s) physiques et {helper} paire(s) de helpers."
        )
        item["controller_review_summary"] = dict(summary)

    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["controller_review_entity_count"] = entity_count
    diagnostic["controller_review_pair_count"] = pair_count
    executive = report.setdefault("executive_summary", {})
    executive["controller_review_entity_count"] = entity_count
    executive["controller_review_pair_count"] = pair_count
    return report


def _patch_quality_gates(report):
    quality = report.get("quality_gates") or {}
    gates = [dict(item) for item in (quality.get("gates") or []) if isinstance(item, dict)]
    sem = report.get("condition_semantics") or {}
    resilience = report.get("resilience_analysis") or {}
    recs = report.get("resilience_recommendations") or {}

    for gate in gates:
        key = str(gate.get("key") or "")
        if key == "condition_semantics":
            physical = int(sem.get("physical_unproven_pair_count", 0) or 0)
            gate["status"] = "warning" if physical else "pass"
            gate["detail"] = (
                f"{sem.get('resolved_pair_count',0)} résolue(s) · "
                f"{sem.get('semantic_v6_resolved_pair_count',0)} par V6 · "
                f"{physical} physique(s) à revoir"
            )
        elif key == "resilience":
            review = int(resilience.get("review_count", 0) or 0)
            partial = int(resilience.get("partial_count", 0) or 0)
            protected = int(resilience.get("protected_count", 0) or 0)
            recommendations = int(recs.get("count", 0) or 0)
            gate["status"] = "warning" if (review or partial or recommendations) else "pass"
            gate["detail"] = (
                f"{protected} protégée(s) · {partial} partielle(s) · "
                f"{review} à revoir · {recommendations} recommandation(s)"
            )

    counts = Counter(str(item.get("status") or "warning") for item in gates)
    quality.update({
        "model": QUALITY_MODEL,
        "gates": gates,
        "counts": dict(counts),
        "overall": "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass"),
    })
    report["quality_gates"] = quality
    return quality


def _sync_executive(report):
    executive = report.setdefault("executive_summary", {})
    sem = report.get("condition_semantics") or {}
    resilience = report.get("resilience_analysis") or {}
    recs = report.get("resilience_recommendations") or {}
    counts = (report.get("action_plan") or {}).get("counts") or {}
    primary = int((report.get("scores") or {}).get("global", 0) or 0)
    preview = int((report.get("score_v5_preview") or {}).get("v5_preview_score", primary) or primary)
    temporal = report.get("temporal_analysis") or {}
    lineage = report.get("entity_lineage") or {}
    root = report.get("root_cause_summary") or {}

    executive.update({
        "condition_semantics_model": CONDITION_MODEL,
        "semantic_v6_resolved_pair_count": int(sem.get("semantic_v6_resolved_pair_count", 0) or 0),
        "supervisory_interlock_pair_count": int(sem.get("supervisory_interlock_pair_count", 0) or 0),
        "mediated_interlock_pair_count": int(sem.get("mediated_interlock_pair_count", 0) or 0),
        "membership_exclusive_pair_count": int(sem.get("membership_exclusive_pair_count", 0) or 0),
        "resilience_model": RESILIENCE_MODEL,
        "resilience_protected_external_count": int(resilience.get("protected_count", 0) or 0),
        "resilience_recommendation_count": int(recs.get("count", 0) or 0),
        "text": (
            f"Indice de santé V4 {primary}/100 ({executive.get('health_label','—')}). "
            f"Preview V5 {preview}/100, non appliqué à l'historique. "
            f"{counts.get('action_now',0)} correction(s) prioritaire(s), "
            f"{counts.get('verify',0)} vérification(s), {counts.get('optimize',0)} optimisation(s). "
            f"Temporal V3.1 : {temporal.get('persistent_count',0)} persistant(s), "
            f"{temporal.get('resolved_since_previous_count',0)} réellement résolu(s). "
            f"Lineage : {lineage.get('confirmed_edge_count',0)} relation(s) confirmée(s), "
            f"{root.get('registry_impacted_automation_count',0)} automatisation(s) corrélée(s). "
            f"Contrôleurs V6 : {sem.get('semantic_v6_resolved_pair_count',0)} paire(s) supplémentaire(s) expliquée(s), "
            f"{sem.get('physical_unproven_pair_count',0)} paire(s) physique(s) restent à revoir. "
            f"Résilience V4 : {resilience.get('protected_count',0)} dépendance(s) externe(s) protégée(s), "
            f"{recs.get('count',0)} recommandation(s) priorisée(s)."
        ),
    })


def _patch_temporal_final(report, history_path):
    """Synchronize the already-created snapshot with the final 0.8.8 plan.

    The earlier temporal layer already wrote this scan. We only replace compact
    diagnostic ID sets; no raw state or YAML content is added.
    """
    plan_ids = sorted(
        str(item.get("id")) for item in (report.get("action_plan") or {}).get("items") or []
        if isinstance(item, dict) and item.get("id")
    )
    all_ids = sorted(
        str(item.get("id")) for item in report.get("diagnostic_explanations") or []
        if isinstance(item, dict) and item.get("id")
    )
    previous_plan = set((report.get("temporal_analysis") or {}).get("active_ids_before_v088") or [])
    current_plan = set(plan_ids)
    removed = sorted(previous_plan - current_plan)

    temporal = report.setdefault("temporal_analysis", {})
    temporal.update({
        "final_plan_synced_v088": True,
        "final_action_plan_diagnostic_count": len(plan_ids),
        "final_all_diagnostic_count": len(all_ids),
        "calibration_removed_ids": removed[:20],
        "calibration_removed_count": len(removed),
    })

    history = load_history(history_path)
    generated_at = str(report.get("generated_at") or "")
    if history and str(history[-1].get("generated_at") or "") == generated_at:
        snap = dict(history[-1])
        before = set(snap.get("active_ids") or [])
        calibration_removed = sorted(before - set(plan_ids))
        snap.update({
            "report_version": VERSION,
            "active_ids": plan_ids,
            "all_diagnostic_ids": all_ids,
            "deescalated_ids": sorted(set(all_ids) - set(plan_ids)),
            "calibration_removed_ids": calibration_removed,
            "condition_semantics_model": CONDITION_MODEL,
            "resilience_model": RESILIENCE_MODEL,
        })
        history[-1] = snap
        save_history(history, history_path)
        temporal["calibration_removed_ids"] = calibration_removed[:20]
        temporal["calibration_removed_count"] = len(calibration_removed)


def _validate_consistency(report):
    failures = []
    sem = report.get("condition_semantics") or {}
    summary = report.get("controller_review_summary") or {}
    resilience = report.get("resilience_analysis") or {}
    plan = report.get("action_plan") or {}
    items = [item for item in plan.get("items") or [] if isinstance(item, dict)]

    unproven = [item for item in sem.get("unproven_pairs") or [] if isinstance(item, dict)]
    if int(sem.get("unproven_pair_count", 0) or 0) != len(unproven):
        failures.append("condition_semantics.unproven_pair_count")
    entities = {str(item.get("entity_id")) for item in unproven if item.get("entity_id")}
    if int(summary.get("pair_count", 0) or 0) != len(unproven):
        failures.append("controller_review_summary.pair_count")
    if int(summary.get("entity_count", 0) or 0) != len(entities):
        failures.append("controller_review_summary.entity_count")

    external = [item for item in resilience.get("items") or [] if item.get("counts_as_external_spof")]
    protected = sum(1 for item in external if item.get("status") == "protected")
    partial = sum(1 for item in external if item.get("status") == "partial")
    review = sum(1 for item in external if item.get("status") == "review")
    if int(resilience.get("protected_count", 0) or 0) != protected:
        failures.append("resilience.protected_count")
    if int(resilience.get("partial_count", 0) or 0) != partial:
        failures.append("resilience.partial_count")
    if int(resilience.get("review_count", 0) or 0) != review:
        failures.append("resilience.review_count")

    counts = _priority_counts(items)
    expected = {key: counts[key] for key in ("action_now", "verify", "optimize")}
    if dict(plan.get("counts") or {}) != expected:
        failures.append("action_plan.counts")
    if int(plan.get("total", len(items)) or 0) != len(items):
        failures.append("action_plan.total")

    existing = report.get("consistency_analysis") or {}
    result = {
        **existing,
        "model": CONSISTENCY_MODEL,
        "status": "fail" if failures else "pass",
        "failure_count": len(failures),
        "failures": failures,
        "checks": {
            **(existing.get("checks") or {}),
            "semantic_v6_pair_identity": "condition_semantics.unproven_pair_count" not in failures,
            "controller_review_identity": not any(item.startswith("controller_review_summary") for item in failures),
            "resilience_role_identity": not any(item.startswith("resilience.") for item in failures),
            "final_plan_identity": not any(item.startswith("action_plan.") for item in failures),
        },
    }
    report["consistency_analysis"] = result
    return result


def _metadata(report):
    report["version"] = VERSION
    schema = report.get("report_schema") or {}
    compatibility = list(schema.get("backward_compatible_with") or [])
    if "0.8.7" not in compatibility:
        compatibility.append("0.8.7")
    capabilities = list(schema.get("capabilities") or [])
    for capability in (
        "controller_semantics_v6",
        "literal_membership_guard_proofs",
        "supervisory_interlock_proofs",
        "mediated_interlock_proofs",
        "role_aware_resilience_v4",
        "fail_closed_numeric_trigger_detection",
        "availability_variable_branch_detection",
        "final_temporal_snapshot_sync_v088",
    ):
        if capability not in capabilities:
            capabilities.append(capability)
    report["report_schema"] = {
        **schema,
        "version": REPORT_SCHEMA,
        "backward_compatible_with": compatibility,
        "capabilities": capabilities,
    }

    report.setdefault("score_meta", {}).update({
        "hardening_version": VERSION,
        "delivery_version": VERSION,
        "condition_semantics_model": CONDITION_MODEL,
        "resilience_model": RESILIENCE_MODEL,
        "resilience_recommendation_model": RECOMMENDATION_MODEL,
        "quality_gate_model": QUALITY_MODEL,
        "score_v5_applied": False,
        "primary_score_model_unchanged": True,
    })
    report.setdefault("diagnostic_engine", {}).update({
        "controller_semantics_v6": True,
        "role_aware_resilience_v4": True,
        "final_temporal_snapshot_sync_v088": True,
    })
    report.setdefault("privacy", {}).update({
        "automatic_configuration_changes": False,
        "semantic_v6_raw_yaml_persisted": False,
        "resilience_v4_raw_states_persisted": False,
        "resilience_v4_raw_yaml_persisted": False,
    })


def enrich_v088(report, history_path="/data/ha-doctor-history.json"):
    if not isinstance(report, dict):
        return report

    # Capture the pre-calibration plan for temporal bookkeeping only.
    temporal = report.setdefault("temporal_analysis", {})
    temporal["active_ids_before_v088"] = [
        str(item.get("id")) for item in (report.get("action_plan") or {}).get("items") or []
        if isinstance(item, dict) and item.get("id")
    ]

    refine_condition_semantics_v6(report)
    build_resilience_analysis_v4(report)
    build_resilience_recommendations_v2(report)
    _sync_action_sections(report)
    _sync_architecture(report)
    _sync_controller_summary(report)
    _patch_temporal_final(report, history_path)
    _sync_executive(report)
    _validate_consistency(report)
    _patch_quality_gates(report)
    _metadata(report)
    return report
