"""HA Doctor 0.14 consolidated product intelligence.

This layer intentionally starts from the stable 0.11 source-derived product
model instead of chaining 0.12 and 0.13 wrappers. Current temporal, semantic and
decision contracts are rebuilt once from the final report.
"""

import product_v110 as source_product
from decision_v140 import build_decision_engine_v2
from contracts_v140 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    PRODUCT_MODEL, TRIAGE_MODEL, TRUST_MODEL, TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY,
    SCORE_TRACE_MODEL, CONDITION_MODEL, CONTROLLER_REVIEW_MODEL, ACTION_PLAN_MODEL,
    ACTION_PLAN_SOURCE, DECISION_MODEL, ENTITY_ATTENTION_MODEL,
)


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def _score_trace(report):
    temporal = report.get("temporal_analysis") or {}
    primary = _int((report.get("scores") or {}).get("global"), 0)
    return {
        "model": SCORE_TRACE_MODEL,
        "primary_score": primary,
        "preview_score": _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), primary),
        "previous_score": temporal.get("previous_score") if temporal.get("previous_score_trusted") else None,
        "score_delta": temporal.get("score_delta") if temporal.get("previous_score_trusted") else None,
        "previous_score_trusted": bool(temporal.get("previous_score_trusted")),
        "previous_score_source": temporal.get("previous_score_source"),
        "comparison_status": temporal.get("score_comparison_status"),
        "latest_candidate_status": temporal.get("latest_candidate_status"),
        "meaningful_previous_generated_at": temporal.get("meaningful_previous_generated_at"),
        "current_generated_at": report.get("generated_at"),
        "history_contract": HISTORY_CONTRACT, "history_policy": HISTORY_POLICY,
        "history_scope": "published_complete_primary_score_only",
        "preview_applied_to_primary": False,
        "false_stability_prevented": bool(temporal.get("false_stability_prevented")),
    }


def _controller_summary(report):
    sem = report.get("condition_semantics") or {}
    remaining = [x for x in sem.get("unproven_pairs") or [] if isinstance(x, dict)]
    physical = [x for x in remaining if str(x.get("target_kind") or "") == "actuator"]
    helpers = [x for x in remaining if str(x.get("target_kind") or "") == "helper"]
    policy = [x for x in physical if (x.get("v9_policy_analysis") or {}).get("status") == "policy_overlap"]
    summary = {
        "model": CONTROLLER_REVIEW_MODEL, "semantic_model": CONDITION_MODEL,
        "entity_count": len({str(x.get("entity_id")) for x in remaining if x.get("entity_id")}),
        "pair_count": len(remaining), "physical_pair_count": len(physical), "helper_pair_count": len(helpers),
        "other_pair_count": max(0, len(remaining) - len(physical) - len(helpers)),
        "mandatory_guard_resolved_pair_count": _int(sem.get("mandatory_guard_resolved_pair_count"), 0),
        "branch_numeric_resolved_pair_count": _int(sem.get("branch_numeric_resolved_pair_count"), 0),
        "policy_overlap_pair_count": len(policy),
        "remaining_physical_entities": sorted({str(x.get("entity_id")) for x in physical if x.get("entity_id")}),
    }
    report["controller_review_summary"] = summary
    for item in (report.get("action_plan") or {}).get("items") or []:
        if isinstance(item, dict) and item.get("id") == "DX-HD-AUTO-003":
            item["controller_review_summary"] = dict(summary)
    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["controller_review_entity_count"] = summary["entity_count"]
    diagnostic["controller_review_pair_count"] = summary["pair_count"]
    return summary


def _public_truth(report, decision):
    return {
        "model": "public_contract_truth_v3_consolidated",
        "version_fresh": report.get("version") == VERSION,
        "report_schema_fresh": (report.get("report_schema") or {}).get("version") == REPORT_SCHEMA,
        "share_schema_fresh": (report.get("share_contract") or {}).get("schema") == SHARE_SCHEMA,
        "diagnostic_source_fresh": (report.get("diagnostic_summary") or {}).get("source") == ACTION_PLAN_SOURCE,
        "action_plan_model_fresh": (report.get("action_plan") or {}).get("model") == ACTION_PLAN_MODEL,
        "controller_review_model_fresh": (report.get("controller_review_summary") or {}).get("model") == CONTROLLER_REVIEW_MODEL,
        "condition_model_fresh": (report.get("condition_semantics") or {}).get("model") == CONDITION_MODEL,
        "temporal_model_fresh": (report.get("temporal_analysis") or {}).get("model") == TEMPORAL_MODEL,
        "decision_model_fresh": decision.get("model") == DECISION_MODEL,
        "history_policy_fresh": (report.get("temporal_analysis") or {}).get("history_policy") == HISTORY_POLICY,
        "decision_item_identity": decision.get("total", 0) == len((report.get("action_plan") or {}).get("items") or []),
    }


def _score_explainer(report, trace):
    status = trace.get("comparison_status"); current = trace.get("primary_score")
    previous = trace.get("previous_score"); delta = trace.get("score_delta")
    if status == "canonical" and previous is not None and delta is not None:
        reason = f"Score primaire {delta:+d} point(s) depuis le dernier rapport publié et validé ({previous} → {current})." if delta else f"Score primaire stable à {current}/100 depuis le dernier rapport publié et validé."
    elif status == "blocked_previous_ignored":
        reason = "Le dernier scan a été bloqué par l'auto-contrôle : il est volontairement ignoré comme référence de score."
    elif status == "legacy_untrusted":
        reason = "Comparaison suspendue : aucun ancien snapshot publié fiable ne respecte encore le contrat de score."
    else:
        reason = "Premier point de comparaison publié fiable : aucun delta n'est encore calculable."
    return {
        "model": "score_change_explainer_v3_publication_aware", "primary_score": current,
        "preview_score": trace.get("preview_score"), "previous_score": previous, "score_delta": delta,
        "previous_score_trusted": bool(trace.get("previous_score_trusted")), "comparison_status": status,
        "reason": reason, "v5_preview_not_applied_to_primary": True,
    }


def _refresh_quality(report, decision):
    quality = report.setdefault("quality_gates", {})
    gates = [x for x in quality.get("gates") or [] if isinstance(x, dict) and x.get("key") != "report_self_check"]
    sem = report.get("condition_semantics") or {}
    for gate in gates:
        if gate.get("key") == "condition_semantics":
            gate["detail"] = (
                f"{sem.get('resolved_pair_count',0)} résolue(s) · {sem.get('branch_numeric_resolved_pair_count',0)} par exclusion numérique · "
                f"{sem.get('policy_overlap_pair_count',0)} overlap(s) de politique · {sem.get('physical_unproven_pair_count',0)} physique(s) à revoir"
            )
    gates.append({
        "key": "decision_engine", "label": "Décision opérationnelle", "status": "pass",
        "detail": f"{decision.get('lane_counts',{}).get('fix_now',0)} à corriger · {decision.get('lane_counts',{}).get('logic_review',0)} logique · {decision.get('lane_counts',{}).get('watch',0)} surveillance",
    })
    quality["gates"] = gates
    return quality


def _rebuild_executive(report, decision, trace):
    executive = report.setdefault("executive_summary", {})
    counts = (report.get("action_plan") or {}).get("counts") or {}
    sem = report.get("condition_semantics") or {}
    security = (report.get("product_intelligence") or {}).get("security") or {}
    maintenance = (report.get("product_intelligence") or {}).get("maintenance") or {}
    attention = decision.get("entity_attention") or {}
    primary = _int((report.get("scores") or {}).get("global"), 0)
    preview = _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), primary)
    status = trace.get("comparison_status")
    if status == "canonical" and trace.get("score_delta") is not None:
        temporal_text = f"score Δ {int(trace.get('score_delta')):+d} depuis le dernier rapport publié."
    elif status == "blocked_previous_ignored":
        temporal_text = "dernier scan bloqué ignoré pour le score."
    else:
        temporal_text = "delta suspendu faute de précédent publié fiable."
    executive.update({
        "product_model": "product_intelligence_v6_consolidated_decision",
        "decision_engine_model": DECISION_MODEL, "temporal_model": TEMPORAL_MODEL,
        "score_history_contract": HISTORY_CONTRACT, "score_history_policy": HISTORY_POLICY,
        "score_comparison_status": status, "previous_score_trusted": bool(trace.get("previous_score_trusted")),
        "controller_policy_overlap_count": _int(sem.get("policy_overlap_pair_count"), 0),
        "registry_zero_impact_watch_count": _int(attention.get("registry_zero_impact_watch_count"), 0),
        "text": (
            f"Indice de santé V4 {primary}/100 ({executive.get('health_label','—')}). Preview V5 {preview}/100, non appliqué au score primaire ; {temporal_text} "
            f"{counts.get('action_now',0)} correction(s) prioritaire(s), {counts.get('verify',0)} vérification(s), {counts.get('optimize',0)} optimisation(s). "
            f"Contrôleurs V9 : {sem.get('physical_unproven_pair_count',0)} paire(s) physique(s) à revoir, dont {sem.get('policy_overlap_pair_count',0)} overlap(s) de politique statique. "
            f"Decision Engine V2 : {decision.get('lane_counts',{}).get('fix_now',0)} fix-now, {decision.get('lane_counts',{}).get('logic_review',0)} revue(s) logique(s), {decision.get('lane_counts',{}).get('watch',0)} surveillance(s). "
            f"Sécurité : {security.get('active_secret_hint_count',0)} indice(s) actif(s) ; maintenance : {maintenance.get('missing_reference_count',0)} référence(s) absente(s)."
        ),
    })


def apply_product_intelligence_v6(report):
    if not isinstance(report, dict):
        return report
    source_product.apply_product_intelligence_v3(report)
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report.setdefault("action_plan", {})["model"] = ACTION_PLAN_MODEL
    report.setdefault("diagnostic_summary", {})["source"] = ACTION_PLAN_SOURCE
    report["diagnostic_summary"]["plan_id_count"] = len((report.get("action_plan") or {}).get("items") or [])
    _controller_summary(report)

    decision = build_decision_engine_v2(report)
    trace = _score_trace(report)
    product = report.setdefault("product_intelligence", {})
    product["model"] = "product_intelligence_v6_consolidated_decision"
    product["score_change_trace"] = trace
    product["score_change_explainer"] = _score_explainer(report, trace)
    product["decision_engine"] = {k: decision.get(k) for k in ("model", "total", "lane_counts", "repair_readiness_counts", "operational_relevance_counts", "primary_action_count", "policy")}
    product["entity_attention"] = decision.get("entity_attention") or {}
    truth = _public_truth(report, decision)
    product["public_contract_truth"] = truth
    product.setdefault("cross_section_truth", {})["public_contracts_fresh"] = all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity"))

    doctor = report.setdefault("doctor_view", {})
    doctor["model"] = PRODUCT_MODEL
    doctor["next_best_actions"] = [
        {
            "id": x.get("id"), "title": x.get("title"), "operational_lane": x.get("operational_lane"),
            "operational_relevance": x.get("operational_relevance"), "execution_priority_score": x.get("execution_priority_score"),
            "confidence": x.get("confidence"), "confidence_score": x.get("confidence_score"),
            "repair_readiness": (x.get("repair_playbook") or {}).get("repair_readiness"),
            "first_manual_step": (((x.get("repair_playbook") or {}).get("steps") or [{}])[0] or {}).get("detail"),
        }
        for x in decision.get("top") or []
    ]
    doctor["decision_summary"] = {
        "model": DECISION_MODEL, "lane_counts": decision.get("lane_counts") or {},
        "watch_external_count": decision.get("watch_external_count", 0),
        "policy_overlap_count": len(decision.get("policy_overlap") or []),
    }
    trust = dict(doctor.get("trust") or report.get("diagnostic_trust") or {})
    trust.update({
        "model": TRUST_MODEL, "decision_engine_complete": decision.get("total", 0) == len(decision.get("items") or []),
        "temporal_score_comparison_trusted": bool(trace.get("previous_score_trusted")),
        "temporal_score_comparison_status": trace.get("comparison_status"),
        "canonical_history_contract": HISTORY_CONTRACT, "canonical_history_policy": HISTORY_POLICY,
        "native_self_check": True, "automatic_fix": False, "read_only": True,
    })
    doctor["trust"] = trust; report["diagnostic_trust"] = trust
    report.setdefault("triage_board", {})["model"] = TRIAGE_MODEL
    report["share_contract"] = {"schema": SHARE_SCHEMA, "model": SHARE_MODEL, "target_bytes": SHARE_TARGET_BYTES, "hard_bytes": SHARE_HARD_BYTES, "single_source_of_truth": True}
    _refresh_quality(report, decision)
    _rebuild_executive(report, decision, trace)

    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for cap in (
        "consolidated_pipeline_v1", "condition_semantics_v9_branch_policy_overlap", "branch_trigger_numeric_profiles",
        "publication_aware_temporal_v5", "blocked_snapshot_baseline_prevention", "decision_engine_v2_operational_lanes",
        "registry_zero_impact_watch_lane", "repair_playbook_v2_evidence_scoped", "native_self_check_v6",
        "share_report_v8_compact_decisions", "public_contract_truth_v3_consolidated",
    ):
        if cap not in capabilities: capabilities.append(cap)
    schema["capabilities"] = capabilities
    return report
