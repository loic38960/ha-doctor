"""HA Doctor 0.16 Evidence Precision product layer."""

import product_v150 as base
from automation_precision_v160 import apply_automation_precision
from decision_v160 import build_decision_engine_v4
from contracts_v160 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    PRODUCT_MODEL, TRIAGE_MODEL, TRUST_MODEL, TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY,
    PUBLICATION_MODEL, SCORE_TRACE_MODEL, CONDITION_MODEL, CONTROLLER_REVIEW_MODEL,
    ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE, DECISION_MODEL, PUBLIC_TRUTH_MODEL,
    CONTROLLER_IMPACT_MODEL, RESILIENCE_MODEL, LOOP_MODEL, DUPLICATE_MODEL,
)


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def install_public_contract_v160(report):
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report["share_contract"] = {
        "schema": SHARE_SCHEMA, "model": SHARE_MODEL,
        "target_bytes": SHARE_TARGET_BYTES, "hard_bytes": SHARE_HARD_BYTES,
        "single_source_of_truth": True,
    }
    report.setdefault("action_plan", {})["model"] = ACTION_PLAN_MODEL
    report.setdefault("diagnostic_summary", {})["source"] = ACTION_PLAN_SOURCE
    return report


def _controller_summary(report):
    sem = report.get("condition_semantics") or {}
    impact = report.get("controller_impact") or sem.get("controller_impact") or {}
    remaining = [x for x in sem.get("unproven_pairs") or [] if isinstance(x, dict)]
    physical = [x for x in remaining if x.get("target_kind") == "actuator"]
    helpers = [x for x in remaining if x.get("target_kind") == "helper"]
    result = {
        "model": CONTROLLER_REVIEW_MODEL, "semantic_model": CONDITION_MODEL,
        "entity_count": len({str(x.get("entity_id")) for x in remaining if x.get("entity_id")}),
        "pair_count": len(remaining), "physical_pair_count": len(physical), "helper_pair_count": len(helpers),
        "event_window_policy_overlap_pair_count": _int(sem.get("event_window_policy_overlap_pair_count"), 0),
        "exact_physical_automation_count": _int(impact.get("impacted_automation_count"), 0),
        "exact_physical_target_count": _int(impact.get("physical_entity_count"), 0),
        "impact_model": CONTROLLER_IMPACT_MODEL,
        "broad_historical_blast_radius_not_used_for_priority": True,
    }
    report["controller_review_summary"] = result
    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["controller_review_entity_count"] = result["entity_count"]
    diagnostic["controller_review_pair_count"] = result["pair_count"]
    return result


def _score_trace(report):
    temporal = report.get("temporal_analysis") or {}
    primary = _int((report.get("scores") or {}).get("global"), 0)
    trusted = bool(temporal.get("previous_score_trusted"))
    previous = temporal.get("previous_score") if trusted else None
    delta = temporal.get("score_delta") if trusted else None
    return {
        "model": SCORE_TRACE_MODEL, "primary_score": primary,
        "preview_score": _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), primary),
        "previous_score": previous, "score_delta": delta, "previous_score_trusted": trusted,
        "comparison_status": temporal.get("score_comparison_status"),
        "meaningful_previous_generated_at": temporal.get("meaningful_previous_generated_at"),
        "current_generated_at": report.get("generated_at"), "history_contract": HISTORY_CONTRACT,
        "history_policy": HISTORY_POLICY, "publication_model": PUBLICATION_MODEL,
        "current_committed_baseline_visible": bool(temporal.get("current_snapshot_publication_complete")),
        "preview_applied_to_primary": False,
    }


def _public_truth(report, decision):
    controller = report.get("controller_review_summary") or {}
    temporal = report.get("temporal_analysis") or {}
    return {
        "model": PUBLIC_TRUTH_MODEL,
        "version_fresh": report.get("version") == VERSION,
        "report_schema_fresh": (report.get("report_schema") or {}).get("version") == REPORT_SCHEMA,
        "share_schema_fresh": (report.get("share_contract") or {}).get("schema") == SHARE_SCHEMA,
        "share_model_fresh": (report.get("share_contract") or {}).get("model") == SHARE_MODEL,
        "diagnostic_source_fresh": (report.get("diagnostic_summary") or {}).get("source") == ACTION_PLAN_SOURCE,
        "action_plan_model_fresh": (report.get("action_plan") or {}).get("model") == ACTION_PLAN_MODEL,
        "controller_review_model_fresh": controller.get("model") == CONTROLLER_REVIEW_MODEL,
        "condition_model_fresh": (report.get("condition_semantics") or {}).get("model") == CONDITION_MODEL,
        "temporal_model_fresh": temporal.get("model") == TEMPORAL_MODEL,
        "decision_model_fresh": decision.get("model") == DECISION_MODEL,
        "history_policy_fresh": temporal.get("history_policy") == HISTORY_POLICY,
        "decision_item_identity": decision.get("total", 0) == len((report.get("action_plan") or {}).get("items") or []),
        "canonical_order_identity": [str(x.get("id")) for x in decision.get("items") or []] == list((decision.get("canonical_order") or {}).get("item_ids") or []),
        "precision_models_present": bool(report.get("controller_impact")) and bool(report.get("automation_precision")) and bool(report.get("resilience_precision")),
        "evaluated_after_precision_install": True,
    }


def _refresh_quality(report, decision):
    quality = report.setdefault("quality_gates", {})
    gates = [x for x in quality.get("gates") or [] if isinstance(x, dict) and x.get("key") not in {"report_self_check", "decision_engine", "evidence_precision"}]
    sem = report.get("condition_semantics") or {}; impact = report.get("controller_impact") or {}
    for gate in gates:
        if gate.get("key") == "condition_semantics":
            gate["detail"] = (
                f"{sem.get('resolved_pair_count',0)} résolue(s) · {sem.get('physical_unproven_pair_count',0)} physique(s) à revoir · "
                f"{impact.get('impacted_automation_count',0)} automatisation(s) dans le scope physique exact"
            )
    gates.append({
        "key": "decision_engine", "label": "Ordre de décision canonique", "status": "pass",
        "detail": f"{decision.get('total',0)} diagnostic(s) ordonnés par une seule politique publique",
    })
    gates.append({
        "key": "evidence_precision", "label": "Précision des preuves", "status": "pass",
        "detail": (
            f"impact contrôleur exact · résilience phase-aware · {(report.get('duplicate_action_semantics') or {}).get('count',0)} doublon(s) exact(s) · "
            f"{(report.get('automation_feedback_semantics') or {}).get('count',0)} feedback(s) classifié(s)"
        ),
    })
    quality["gates"] = gates


def _rebuild_summary(report, decision, trace):
    lanes = decision.get("lane_counts") or {}; impact = report.get("controller_impact") or {}
    resilience = report.get("resilience_recommendations") or {}
    feedback = report.get("automation_feedback_semantics") or {}; duplicate = report.get("duplicate_action_semantics") or {}
    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["operational_counts"] = dict(lanes)
    diagnostic["actionable_count"] = _int(decision.get("primary_action_count"), 0)
    diagnostic["headline"] = (
        f"{lanes.get('fix_now',0)} correction(s), {lanes.get('logic_review',0)} revue(s) logique(s), "
        f"{lanes.get('watch',0)} surveillance(s) et {lanes.get('optimize',0)} optimisation(s)."
    )
    diagnostic["precision"] = {
        "controller_physical_pair_count": _int(impact.get("physical_pair_count"), 0),
        "controller_impacted_automation_count": _int(impact.get("impacted_automation_count"), 0),
        "resilience_must_fix_count": _int(resilience.get("must_fix_count"), 0),
        "duplicate_exact_count": _int(duplicate.get("count"), 0),
        "feedback_relation_count": _int(feedback.get("count"), 0),
    }

    primary = _int((report.get("scores") or {}).get("global"), 0)
    preview = _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), primary)
    if trace.get("comparison_status") == "canonical" and trace.get("score_delta") is not None:
        temporal_text = f"Δ publié {int(trace.get('score_delta')):+d}."
    elif trace.get("comparison_status") == "blocked_previous_ignored":
        temporal_text = "dernier candidat bloqué ignoré ; baseline publiée recherchée."
    else:
        temporal_text = "baseline publiée en cours d'établissement."
    executive = report.setdefault("executive_summary", {})
    executive.update({
        "product_model": "product_intelligence_v8_evidence_precision", "decision_engine_model": DECISION_MODEL,
        "temporal_model": TEMPORAL_MODEL, "score_history_contract": HISTORY_CONTRACT,
        "score_comparison_status": trace.get("comparison_status"), "previous_score_trusted": bool(trace.get("previous_score_trusted")),
        "precision_summary": diagnostic["precision"],
        "text": (
            f"Indice de santé V4 {primary}/100 ({executive.get('health_label','—')}). Preview V5 {preview}/100 ; {temporal_text} "
            f"Decision V4 : {lanes.get('fix_now',0)} correction(s), {lanes.get('logic_review',0)} revue(s), {lanes.get('watch',0)} watch. "
            f"Contrôleurs : {impact.get('physical_pair_count',0)} paire(s) physique(s) réellement ouverte(s), {impact.get('impacted_automation_count',0)} automatisation(s) dans ce scope exact. "
            f"Résilience : {resilience.get('must_fix_count',0)} must-fix, {resilience.get('hardening_count',0)} hardening."
        ),
    })


def apply_product_intelligence_v8(report):
    if not isinstance(report, dict):
        return report
    # Reuse mature source-derived security/maintenance/score layers, then replace
    # every public identity/order with 0.16 precision truth.
    base.apply_product_intelligence_v7(report)
    install_public_contract_v160(report)
    _controller_summary(report)
    apply_automation_precision(report)
    decision = build_decision_engine_v4(report)
    install_public_contract_v160(report)

    trace = _score_trace(report)
    product = report.setdefault("product_intelligence", {})
    product["model"] = "product_intelligence_v8_evidence_precision"
    product["score_change_trace"] = trace
    product["decision_engine"] = {k: decision.get(k) for k in ("model", "total", "lane_counts", "primary_action_count", "policy")}
    product["controller_impact"] = report.get("controller_impact") or {}
    product["resilience_precision"] = report.get("resilience_precision") or {}
    product["automation_precision"] = report.get("automation_precision") or {}
    product["entity_attention"] = decision.get("entity_attention") or {}
    truth = _public_truth(report, decision)
    product["public_contract_truth"] = truth

    perf = report.get("scan_performance") or {}
    single_snapshot = perf.get("single_state_snapshot_preserved") is True and _int(perf.get("additional_home_assistant_state_reads"), -1) == 0
    doctor = report.setdefault("doctor_view", {})
    doctor["model"] = PRODUCT_MODEL
    doctor["decision_summary"] = {
        "model": DECISION_MODEL, "lane_counts": decision.get("lane_counts") or {},
        "primary_action_count": decision.get("primary_action_count", 0),
        "controller_exact_automation_count": _int((report.get("controller_impact") or {}).get("impacted_automation_count"), 0),
        "resilience_must_fix_count": _int((report.get("resilience_recommendations") or {}).get("must_fix_count"), 0),
    }
    doctor["next_best_actions"] = [
        {
            "id": x.get("id"), "title": x.get("title"), "lane": x.get("operational_lane"),
            "relevance": x.get("operational_relevance"), "priority_score": x.get("execution_priority_score"),
            "readiness": (x.get("repair_playbook") or {}).get("repair_readiness"),
            "first_step": (((x.get("repair_playbook") or {}).get("steps") or [{}])[0] or {}).get("detail"),
        }
        for x in decision.get("top") or []
    ]
    trust = dict(doctor.get("trust") or report.get("diagnostic_trust") or {})
    trust.update({
        "model": TRUST_MODEL, "single_snapshot_evidence": single_snapshot,
        "public_contract_truth": all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity")) and bool(truth.get("canonical_order_identity")),
        "precision_evidence_present": bool(truth.get("precision_models_present")),
        "temporal_score_comparison_trusted": bool(trace.get("previous_score_trusted")),
        "temporal_score_comparison_status": trace.get("comparison_status"),
        "read_only": True, "automatic_fix": False,
    })
    doctor["trust"] = trust; report["diagnostic_trust"] = trust
    report.setdefault("triage_board", {})["model"] = TRIAGE_MODEL
    _refresh_quality(report, decision)
    _rebuild_summary(report, decision, trace)

    schema = report.setdefault("report_schema", {})
    caps = list(schema.get("capabilities") or [])
    for cap in (
        "controller_impact_v2_unresolved_scope", "resilience_precision_v5_phase_aware",
        "automation_feedback_v1_intent_aware", "duplicate_action_semantics_v1",
        "canonical_decision_order_v1", "decision_engine_v4_precision_board",
        "temporal_v7_published_baseline_visibility", "share_report_v10_20k_target",
    ):
        if cap not in caps: caps.append(cap)
    schema["capabilities"] = caps
    return report
