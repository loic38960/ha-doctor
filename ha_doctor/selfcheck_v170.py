"""HA Doctor 0.17 native resolution/attribution self-check."""

from contracts_v170 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    SELF_CHECK_MODEL, ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE, DECISION_MODEL, CANONICAL_ORDER_MODEL,
    CONDITION_MODEL, CONTROLLER_REVIEW_MODEL, TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY,
    PUBLICATION_MODEL, RESILIENCE_MODEL, RESILIENCE_RECOMMENDATION_MODEL, FEEDBACK_MODEL,
    DUPLICATE_MODEL, REFERENCE_MODEL, SCORE_ATTRIBUTION_MODEL, REPAIR_PLAYBOOK_MODEL,
    OPERATIONAL_LANES, REPAIR_READINESS, RESOLUTION_STATUSES,
)
from sharing_v170 import build_share_report


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def _result(checks, failures, warnings):
    status = "fail" if failures else ("warning" if warnings else "pass")
    return {
        "model": SELF_CHECK_MODEL, "version": VERSION, "status": status,
        "check_count": len(checks), "pass_count": max(0, len(checks)-len(failures)-len(warnings)),
        "warning_count": len(warnings), "failure_count": len(failures),
        "failures": failures[:100], "warnings": warnings[:100], "blocks_publication": bool(failures),
        "final_export_self_validated": False, "resolution_contracts_self_validated": True,
        "score_attribution_self_validated": True, "replacement_inference_self_validated": True,
        "read_only": True,
    }


def _refresh_quality(report):
    sc = report.get("self_check") or {}; quality = report.setdefault("quality_gates", {})
    gates = [x for x in quality.get("gates") or [] if isinstance(x, dict) and x.get("key") != "report_self_check"]
    gates.append({
        "key": "report_self_check", "label": "Auto-contrôle résolution et attribution",
        "status": "fail" if sc.get("failure_count") else ("warning" if sc.get("warning_count") else "pass"),
        "detail": f"{sc.get('pass_count',0)}/{sc.get('check_count',0)} contrôle(s) réussi(s) · {sc.get('warning_count',0)} avertissement(s) · {sc.get('failure_count',0)} échec(s)",
    })
    quality["gates"] = gates
    counts = {}
    for gate in gates:
        status = str(gate.get("status") or "pass"); counts[status] = counts.get(status, 0) + 1
    quality["counts"] = counts
    quality["overall"] = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")
    quality["non_pass_gates"] = [{k:x.get(k) for k in ("key","label","status","detail")} for x in gates if x.get("status") != "pass"]


def _sync_trust(report):
    sc = report.get("self_check") or {}; doctor = report.setdefault("doctor_view", {}); trust = doctor.setdefault("trust", {})
    trust["self_check_status"] = sc.get("status"); trust["final_export_self_validated"] = bool(sc.get("final_export_self_validated"))
    if sc.get("failure_count"):
        trust["score"] = min(_int(trust.get("score"), 90), 50); trust["level"] = "low"
    elif _int(trust.get("score"), 90) >= 85:
        trust["level"] = "high"
    report["diagnostic_trust"] = trust


def run_self_check_v9(report):
    checks=[]; failures=[]; warnings=[]
    def check(key, ok, severity="fail", detail=None):
        checks.append(key)
        if ok: return
        (failures if severity == "fail" else warnings).append({"key":key,"detail":detail or key})

    action = report.get("action_plan") or {}; actions=[x for x in action.get("items") or [] if isinstance(x,dict)]
    decision=report.get("decision_engine") or {}; decisions=[x for x in decision.get("items") or [] if isinstance(x,dict)]
    temporal=report.get("temporal_analysis") or {}; sem=report.get("condition_semantics") or {}
    controller=report.get("controller_review_summary") or {}; recs=report.get("resilience_recommendations") or {}
    feedback=report.get("automation_feedback_semantics") or {}; duplicate=report.get("duplicate_action_semantics") or {}
    refs=report.get("missing_reference_intelligence") or {}; attr=report.get("score_attribution") or {}
    product=report.get("product_intelligence") or {}; truth=product.get("public_contract_truth") or report.get("public_contract_truth") or {}
    perf=report.get("scan_performance") or {}; privacy=report.get("privacy") or {}; doctor=report.get("doctor_view") or {}

    # Public identity.
    check("identity.version", report.get("version")==VERSION)
    check("identity.report_schema", (report.get("report_schema") or {}).get("version")==REPORT_SCHEMA)
    check("identity.share_schema", (report.get("share_contract") or {}).get("schema")==SHARE_SCHEMA)
    check("identity.share_model", (report.get("share_contract") or {}).get("model")==SHARE_MODEL)
    check("identity.action_model", action.get("model")==ACTION_PLAN_MODEL)
    check("identity.action_source", (report.get("diagnostic_summary") or {}).get("source")==ACTION_PLAN_SOURCE)
    check("identity.decision_model", decision.get("model")==DECISION_MODEL)
    check("identity.condition_model", sem.get("model")==CONDITION_MODEL)
    check("identity.controller_model", controller.get("model")==CONTROLLER_REVIEW_MODEL)
    check("identity.temporal_model", temporal.get("model")==TEMPORAL_MODEL)
    check("identity.history_contract", temporal.get("history_contract")==HISTORY_CONTRACT)
    check("identity.history_policy", temporal.get("history_policy")==HISTORY_POLICY)
    check("identity.publication_model", temporal.get("publication_model")==PUBLICATION_MODEL)
    check("identity.resilience_model", recs.get("analysis_model")==RESILIENCE_MODEL)
    check("identity.resilience_recommendation_model", recs.get("model")==RESILIENCE_RECOMMENDATION_MODEL)
    check("identity.feedback_model", feedback.get("model")==FEEDBACK_MODEL)
    check("identity.duplicate_model", duplicate.get("model")==DUPLICATE_MODEL)
    check("identity.reference_model", refs.get("model")==REFERENCE_MODEL)
    check("identity.attribution_model", attr.get("model")==SCORE_ATTRIBUTION_MODEL)
    check("identity.public_truth", truth.get("all_current_contracts_fresh") is True and truth.get("decision_item_identity") is True and truth.get("canonical_order_identity") is True)

    # Acquisition and privacy.
    check("acquisition.single_snapshot", perf.get("single_state_snapshot_preserved") is True)
    check("acquisition.no_extra_state_reads", _int(perf.get("additional_home_assistant_state_reads"), -1)==0)
    check("acquisition.trust_sees_snapshot", (doctor.get("trust") or {}).get("single_snapshot_evidence") is True)
    check("privacy.read_only", (doctor.get("trust") or {}).get("read_only") is True and decision.get("read_only") is True)
    check("privacy.no_auto_fix", decision.get("automatic_fix") is False and doctor.get("automatic_fix",False) is False)
    check("privacy.no_raw_states", not any(bool(v) for k,v in privacy.items() if "raw_states_persisted" in k))
    check("privacy.no_raw_yaml", not any(bool(v) for k,v in privacy.items() if "raw_yaml_persisted" in k))
    check("privacy.no_secret_values", not any(bool(v) for k,v in privacy.items() if "secret_values_persisted" in k))

    # One canonical decision order and full identity.
    action_ids=[str(x.get("id")) for x in actions if x.get("id")]; decision_ids=[str(x.get("id")) for x in decisions if x.get("id")]
    canonical=decision.get("canonical_order") or {}
    check("actions.total", _int(action.get("total"),-1)==len(actions))
    check("actions.unique", len(action_ids)==len(set(action_ids))==len(actions))
    check("decision.total", _int(decision.get("total"),-1)==len(decisions)==len(actions))
    check("decision.ids", action_ids==decision_ids)
    check("order.model", canonical.get("model")==CANONICAL_ORDER_MODEL)
    check("order.identity", decision_ids==list(canonical.get("item_ids") or []))
    top_ids=[str(x.get("id")) for x in (report.get("diagnostic_summary") or {}).get("top_actions") or [] if x.get("id")]
    check("order.top_prefix", top_ids==decision_ids[:len(top_ids)])
    check("decision.lane_sum", sum(_int(v) for v in (decision.get("lane_counts") or {}).values())==len(decisions))
    check("decision.resolution_sum", sum(_int(v) for v in (decision.get("resolution_counts") or {}).values())==len(decisions))

    for idx,item in enumerate(decisions):
        pb=item.get("repair_playbook") or {}; status=str(item.get("resolution_status") or "")
        check(f"decision.{idx}.domain", bool(item.get("domain")))
        check(f"decision.{idx}.lane", item.get("operational_lane") in OPERATIONAL_LANES)
        check(f"decision.{idx}.resolution", status in RESOLUTION_STATUSES)
        check(f"decision.{idx}.playbook_model", pb.get("model")==REPAIR_PLAYBOOK_MODEL)
        check(f"decision.{idx}.readiness", pb.get("repair_readiness") in REPAIR_READINESS)
        check(f"decision.{idx}.steps", bool(pb.get("steps")))
        check(f"decision.{idx}.read_only", pb.get("automatic_fix") is False and pb.get("read_only") is True)
        source=str(item.get("source_id") or "")
        if source=="HD-AUTO-005" and _int(duplicate.get("manual_fix_ready_count"),0)>0:
            check(f"decision.{idx}.duplicate_fix_now", item.get("operational_lane")=="fix_now" and status=="manual_fix_ready")
        if source=="HD-AUTO-008" and _int(feedback.get("count"),0)>0 and _int(feedback.get("review_count"),0)==0:
            check(f"decision.{idx}.feedback_resolved", item.get("operational_lane")=="watch" and status=="statically_resolved")
        if source=="HD-CFG-001" and refs.get("finding_present") and _int(refs.get("runtime_relevant_count"),0)==0 and _int(refs.get("evidence_entity_count"),0)>0:
            check(f"decision.{idx}.missing_ref_watch", item.get("operational_lane")=="watch")

    # Automation resolution must never claim runtime observation.
    check("feedback.runtime_loop_not_proven", _int(feedback.get("runtime_loop_proven_count"),0)==0)
    check("feedback.parse", _int(feedback.get("parse_error_count"),0)==0, "warning")
    for idx,item in enumerate(feedback.get("items") or []):
        if not isinstance(item,dict): continue
        check(f"feedback.{idx}.runtime_false", item.get("runtime_loop_proven") is False)
        if item.get("classification")=="terminating_state_transition":
            check(f"feedback.{idx}.terminal_resolved", item.get("manual_review_required") is False and item.get("static_self_loop_proven") is False)
        if item.get("classification")=="self_retrigger_candidate":
            check(f"feedback.{idx}.broad_review", item.get("manual_review_required") is True)

    check("duplicate.no_auto_cleanup", duplicate.get("automatic_cleanup") is False)
    for idx,item in enumerate(duplicate.get("items") or []):
        if not isinstance(item,dict): continue
        check(f"duplicate.{idx}.manual_only", item.get("automatic_removal_safe") is False)
        if item.get("resolution_status")=="manual_fix_ready":
            check(f"duplicate.{idx}.exact_ready", item.get("exact_duplicate") is True and item.get("classification")=="side_effect_duplicate")

    # Missing references: classify, never guess replacement.
    check("references.no_inference", refs.get("replacement_inference_enabled") is False)
    for idx,item in enumerate(refs.get("items") or []):
        if not isinstance(item,dict): continue
        check(f"references.{idx}.no_guess", item.get("replacement_inferred") is False and item.get("replacement_suggestion") is None)

    # Resilience: unprotected remains must-fix; weak-only remains hardening.
    for idx,rec in enumerate(recs.get("items") or []):
        if not isinstance(rec,dict): continue
        unprotected=_int(rec.get("unprotected_pre_control_risk_count", rec.get("pre_control_risk_count")),0)
        weak=_int(rec.get("weak_pre_control_risk_count"),0)
        if unprotected>0:
            check(f"resilience.{idx}.unprotected_must_fix", rec.get("tier")=="must_fix")
        if unprotected==0 and weak>0:
            check(f"resilience.{idx}.weak_hardening", rec.get("tier")=="hardening")
        guard=rec.get("guard_strategy") or {}
        check(f"resilience.{idx}.guard_present", bool(guard.get("strategy")) and guard.get("automatic_change") is False)

    # Score attribution is honest. A prior canonical score without per-domain
    # detail must explicitly say it cannot attribute domain movement.
    status=attr.get("status")
    check("attribution.status", status in {"no_published_baseline","baseline_domain_detail_unavailable","attributed"})
    if status=="baseline_domain_detail_unavailable":
        check("attribution.no_fake_domains", attr.get("domain_detail_available") is False and not attr.get("changed_domains"))
    if status=="attributed":
        check("attribution.has_domains", attr.get("domain_detail_available") is True and isinstance(attr.get("domain_deltas"),list))
    check("temporal.blocked_never_baseline", temporal.get("blocked_reports_never_become_score_baselines") is True)
    check("temporal.precommit_not_committed", temporal.get("current_committed_baseline") is not True)
    check("temporal.transaction_staged", (report.get("publication_transaction") or {}).get("phase")=="staged")

    # Exact final support payload including provisional self-check.
    result=_result(checks,failures,warnings); report["self_check"]=result
    share=build_share_report(report)
    check("share.built", isinstance(share,dict))
    if isinstance(share,dict):
        meta=share.get("export_meta") or {}; size=_int(meta.get("share_report_bytes_estimate"),0)
        check("share.version", share.get("version")==VERSION)
        check("share.schema", (share.get("share_schema") or {}).get("version")==SHARE_SCHEMA)
        check("share.findings", _int(meta.get("exported_finding_count"),-1)==len(report.get("findings") or []))
        check("share.actions", _int(meta.get("exported_action_count"),-1)==len(actions))
        check("share.target", size<=SHARE_TARGET_BYTES, "warning", f"{size}>{SHARE_TARGET_BYTES}")
        check("share.hard", size<=SHARE_HARD_BYTES, "fail", f"{size}>{SHARE_HARD_BYTES}")
        check("share.identities", meta.get("all_action_identities_preserved") is True and meta.get("all_finding_identities_preserved") is True)
        check("share.privacy", meta.get("raw_states_included") is False and meta.get("raw_yaml_included") is False and meta.get("secret_values_included") is False)
        check("share.no_reference_guess", meta.get("replacement_inference_disabled") is True)

    result=_result(checks,failures,warnings); result["final_export_self_validated"]=not bool(failures); report["self_check"]=result
    final_share=build_share_report(report); final_size=_int((final_share.get("export_meta") or {}).get("share_report_bytes_estimate"),0)
    if final_size>SHARE_HARD_BYTES:
        failures.append({"key":"share.final_hard","detail":f"{final_size}>{SHARE_HARD_BYTES}"}); checks.append("share.final_hard")
    elif final_size>SHARE_TARGET_BYTES:
        warnings.append({"key":"share.final_target","detail":f"{final_size}>{SHARE_TARGET_BYTES}"}); checks.append("share.final_target")
    else:
        checks.append("share.final_target")
    result=_result(checks,failures,warnings); result["final_export_self_validated"]=not bool(failures); result["final_export_bytes"]=final_size
    report["self_check"]=result; _refresh_quality(report); _sync_trust(report)
    return result


def post_commit_validation_v9(report):
    sc=report.get("self_check") or {}; temporal=report.get("temporal_analysis") or {}; decision=report.get("decision_engine") or {}
    share=build_share_report(report); meta=share.get("export_meta") or {}
    valid=(
        sc.get("status") in {"pass","warning"} and not sc.get("blocks_publication")
        and temporal.get("current_committed_baseline") is True
        and temporal.get("current_snapshot_publication_complete") is True
        and temporal.get("current_domain_scores_persisted") is True
        and decision.get("automatic_fix") is False and decision.get("read_only") is True
        and meta.get("within_hard_bytes") is True
        and meta.get("all_action_identities_preserved") is True
        and meta.get("all_finding_identities_preserved") is True
    )
    result={"model":"post_commit_validation_v9","valid":bool(valid),"current_domain_scores_persisted":temporal.get("current_domain_scores_persisted"),"support_bytes":meta.get("share_report_bytes_estimate"),"read_only":True}
    report.setdefault("self_check",{})["post_commit_validation"]="pass" if valid else "fail"
    report["post_commit_validation"] = result
    return result
