"""HA Doctor 0.17 Resolution & Attribution product layer."""

from collections import Counter
from product_v160 import apply_product_intelligence_v8
from automation_resolution_v170 import apply_automation_resolution
from reference_intelligence_v170 import build_missing_reference_intelligence
from resilience_v170 import refine_resilience_v6
from decision_v170 import build_decision_engine_v5
from contracts_v170 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL,
    PRODUCT_MODEL, TRUST_MODEL, PUBLIC_TRUTH_MODEL, ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE,
    DECISION_MODEL, CONDITION_MODEL, CONTROLLER_REVIEW_MODEL, TEMPORAL_MODEL,
    RESILIENCE_MODEL, RESILIENCE_RECOMMENDATION_MODEL, FEEDBACK_MODEL, DUPLICATE_MODEL,
    REFERENCE_MODEL, SCORE_ATTRIBUTION_MODEL, REPAIR_PLAYBOOK_MODEL,
)


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def install_public_contract_v170(report):
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report["share_contract"] = {"schema": SHARE_SCHEMA, "model": SHARE_MODEL, "source_report_version": VERSION}
    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["source"] = ACTION_PLAN_SOURCE
    report.setdefault("action_plan", {})["model"] = ACTION_PLAN_MODEL
    report.setdefault("condition_semantics", {})["model"] = CONDITION_MODEL
    controller = report.setdefault("controller_review_summary", {})
    controller["model"] = CONTROLLER_REVIEW_MODEL
    controller["semantic_model"] = CONDITION_MODEL
    report.setdefault("temporal_analysis", {})["model"] = TEMPORAL_MODEL
    return report


def _public_truth(report):
    decision = report.get("decision_engine") or {}
    action = report.get("action_plan") or {}
    temporal = report.get("temporal_analysis") or {}
    feedback = report.get("automation_feedback_semantics") or {}
    duplicate = report.get("duplicate_action_semantics") or {}
    refs = report.get("missing_reference_intelligence") or {}
    recs = report.get("resilience_recommendations") or {}
    controller = report.get("controller_review_summary") or {}
    sem = report.get("condition_semantics") or {}
    decisions = [x for x in decision.get("items") or [] if isinstance(x, dict)]
    actions = [x for x in action.get("items") or [] if isinstance(x, dict)]
    result = {
        "model": PUBLIC_TRUTH_MODEL,
        "version_fresh": report.get("version") == VERSION,
        "report_schema_fresh": (report.get("report_schema") or {}).get("version") == REPORT_SCHEMA,
        "share_schema_fresh": (report.get("share_contract") or {}).get("schema") == SHARE_SCHEMA,
        "share_model_fresh": (report.get("share_contract") or {}).get("model") == SHARE_MODEL,
        "diagnostic_source_fresh": (report.get("diagnostic_summary") or {}).get("source") == ACTION_PLAN_SOURCE,
        "action_plan_model_fresh": action.get("model") == ACTION_PLAN_MODEL,
        "controller_review_model_fresh": controller.get("model") == CONTROLLER_REVIEW_MODEL,
        "condition_model_fresh": sem.get("model") == CONDITION_MODEL,
        "temporal_model_fresh": temporal.get("model") == TEMPORAL_MODEL,
        "decision_model_fresh": decision.get("model") == DECISION_MODEL,
        "feedback_model_fresh": feedback.get("model") == FEEDBACK_MODEL,
        "duplicate_model_fresh": duplicate.get("model") == DUPLICATE_MODEL,
        "reference_model_fresh": refs.get("model") == REFERENCE_MODEL,
        "resilience_model_fresh": recs.get("analysis_model") == RESILIENCE_MODEL,
        "resilience_recommendation_model_fresh": recs.get("model") == RESILIENCE_RECOMMENDATION_MODEL,
        "score_attribution_model_fresh": (report.get("score_attribution") or {}).get("model") == SCORE_ATTRIBUTION_MODEL,
        "decision_item_identity": {str(x.get("id")) for x in decisions} == {str(x.get("id")) for x in actions},
        "canonical_order_identity": [str(x.get("id")) for x in decisions] == list((decision.get("canonical_order") or {}).get("item_ids") or []),
        "playbook_contract_fresh": all((x.get("repair_playbook") or {}).get("model") == REPAIR_PLAYBOOK_MODEL for x in decisions),
        "replacement_inference_disabled": refs.get("replacement_inference_enabled") is False,
        "automatic_fix_disabled": decision.get("automatic_fix") is False,
    }
    result["all_current_contracts_fresh"] = all(bool(v) for k, v in result.items() if k.endswith("_fresh"))
    return result


def _trust(report, truth):
    perf = report.get("scan_performance") or {}
    flow = report.get("flow_confidence") or {}
    lineage = report.get("entity_lineage") or report.get("entity_lineage_summary") or {}
    score = 90
    deductions = []
    if perf.get("single_state_snapshot_preserved") is not True:
        score -= 30; deductions.append("single_snapshot_not_proven")
    if flow and flow.get("quality_status") not in {None, "pass"}:
        score -= 15; deductions.append("flow_not_pass")
    if _int(lineage.get("parse_error_count"), 0) > 0:
        score -= 10; deductions.append("lineage_parse_errors")
    if not truth.get("all_current_contracts_fresh") or not truth.get("decision_item_identity") or not truth.get("canonical_order_identity"):
        score -= 30; deductions.append("public_contract_truth_failure")
    temporal = report.get("temporal_analysis") or {}
    return {
        "model": TRUST_MODEL, "score": max(0, score),
        "level": "high" if score >= 85 else ("medium" if score >= 65 else "low"),
        "read_only": True, "single_snapshot_evidence": perf.get("single_state_snapshot_preserved") is True,
        "public_contract_truth": not deductions or "public_contract_truth_failure" not in deductions,
        "self_check_status": ((report.get("self_check") or {}).get("status") or "pending"),
        "final_export_self_validated": bool((report.get("self_check") or {}).get("final_export_self_validated")),
        "temporal_score_comparison_trusted": temporal.get("previous_score_trusted") is True,
        "temporal_score_comparison_status": temporal.get("score_comparison_status") or temporal.get("comparison_status"),
        "score_attribution_status": (report.get("score_attribution") or {}).get("status"),
        "deduction_reasons": deductions,
        "automatic_fix": False,
    }


def _operational_summary(report):
    decision = report.get("decision_engine") or {}
    resolutions = decision.get("resolution_counts") or {}
    lanes = decision.get("lane_counts") or {}
    return {
        "model": "operational_summary_v2_resolution",
        "lane_counts": dict(lanes), "resolution_counts": dict(resolutions),
        "primary_action_count": decision.get("primary_action_count", 0),
        "manual_fix_ready_count": resolutions.get("manual_fix_ready", 0),
        "logic_review_required_count": resolutions.get("logic_review_required", 0),
        "statically_resolved_count": resolutions.get("statically_resolved", 0),
        "watch_only_count": resolutions.get("watch_only", 0),
        "duplicate_manual_fix_ready_count": (report.get("duplicate_action_semantics") or {}).get("manual_fix_ready_count", 0),
        "feedback_statically_resolved_count": (report.get("automation_feedback_semantics") or {}).get("statically_resolved_count", 0),
        "missing_reference_runtime_relevant_count": (report.get("missing_reference_intelligence") or {}).get("runtime_relevant_count", 0),
    }


def _sync_diagnostic_summary(report, summary):
    decision = report.get("decision_engine") or {}
    diagnostic = report.setdefault("diagnostic_summary", {})
    lanes = decision.get("lane_counts") or {}
    diagnostic["operational_counts"] = {k: _int(lanes.get(k), 0) for k in ("fix_now", "logic_review", "watch", "optimize", "restore_if_needed") if _int(lanes.get(k), 0)}
    diagnostic["actionable_count"] = _int(lanes.get("fix_now"), 0) + _int(lanes.get("logic_review"), 0) + _int(lanes.get("restore_if_needed"), 0) + _int(lanes.get("optimize"), 0)
    diagnostic["headline"] = (
        f"{_int(lanes.get('fix_now'),0)} correction(s), {_int(lanes.get('logic_review'),0)} revue(s) logique(s), "
        f"{_int(lanes.get('watch'),0)} surveillance(s) et {_int(lanes.get('optimize'),0)} optimisation(s)."
    )
    diagnostic["source"] = ACTION_PLAN_SOURCE
    diagnostic["resolution"] = summary


def _executive(report, summary):
    scores = report.get("scores") or {}
    preview = report.get("score_v5_preview") or {}
    executive = report.setdefault("executive_summary", {})
    executive["health_score"] = scores.get("global")
    executive["score_v5_preview"] = preview.get("v5_preview_score") or preview.get("v5_preview_score_raw")
    executive["resolution_summary"] = summary
    attribution = report.get("score_attribution") or {}
    executive["score_attribution"] = {
        "status": attribution.get("status"), "primary_delta": attribution.get("primary_delta"),
        "domain_detail_available": attribution.get("domain_detail_available"),
        "changed_domains": (attribution.get("changed_domains") or [])[:6],
    }
    executive["text"] = (
        f"Indice de santé {scores.get('global','—')}/100. Decision V5 : {summary.get('manual_fix_ready_count',0)} correction(s) manuelle(s) prête(s), "
        f"{summary.get('logic_review_required_count',0)} revue(s) logique(s), {summary.get('statically_resolved_count',0)} relation(s) résolue(s) statiquement. "
        f"Attribution score : {attribution.get('status','indisponible')}."
    )


def apply_product_intelligence_v9(report):
    # Reuse mature 0.16 product calculations first, then replace the decision
    # layer with V0.17 resolution-aware evidence. No HA read occurs here.
    apply_product_intelligence_v8(report)
    install_public_contract_v170(report)
    apply_automation_resolution(report)
    build_missing_reference_intelligence(report)
    refine_resilience_v6(report)
    decision = build_decision_engine_v5(report)
    install_public_contract_v170(report)

    summary = _operational_summary(report)
    _sync_diagnostic_summary(report, summary)
    _executive(report, summary)
    truth = _public_truth(report)
    trust = _trust(report, truth)
    product = {
        "model": "product_intelligence_v9_resolution_attribution",
        "security": (report.get("product_intelligence") or {}).get("security") or {},
        "maintenance": (report.get("product_intelligence") or {}).get("maintenance") or {},
        "controller_impact": report.get("controller_impact") or {},
        "resilience_precision": report.get("resilience_precision") or {},
        "automation_resolution": report.get("automation_resolution") or {},
        "missing_reference_intelligence": report.get("missing_reference_intelligence") or {},
        "score_attribution": report.get("score_attribution") or {},
        "public_contract_truth": truth,
    }
    report["product_intelligence"] = product
    report["public_contract_truth"] = truth
    report["diagnostic_trust"] = trust
    report["doctor_view"] = {
        "model": PRODUCT_MODEL,
        "verdict": (report.get("doctor_view") or {}).get("verdict") or {"code": "action_required", "label": "Corrections prioritaires"},
        "technical_health_score": (report.get("scores") or {}).get("global"),
        "trust": trust,
        "decision_summary": {"model": DECISION_MODEL, **summary},
        "automatic_fix": False, "read_only": True,
    }
    report["resolution_summary"] = summary
    return product
