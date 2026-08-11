"""HA Doctor 0.16 native precision self-check."""

from contracts_v160 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    SELF_CHECK_MODEL, CONDITION_MODEL, CONTROLLER_REVIEW_MODEL, CONTROLLER_IMPACT_MODEL,
    ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE, DECISION_MODEL, CANONICAL_ORDER_MODEL,
    TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL,
    RESILIENCE_MODEL, RESILIENCE_RECOMMENDATION_MODEL, LOOP_MODEL, DUPLICATE_MODEL,
    REPAIR_PLAYBOOK_MODEL, OPERATIONAL_LANES, REPAIR_READINESS,
)
from sharing_v160 import build_share_report
from product_v110 import finding_evidence_count


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def _finding_map(report):
    return {str(x.get("rule_id")): x for x in report.get("findings") or [] if isinstance(x, dict) and x.get("rule_id")}


def _result(checks, failures, warnings):
    status = "fail" if failures else ("warning" if warnings else "pass")
    return {
        "model": SELF_CHECK_MODEL, "version": VERSION, "status": status,
        "check_count": len(checks), "pass_count": max(0, len(checks) - len(failures) - len(warnings)),
        "warning_count": len(warnings), "failure_count": len(failures),
        "failures": failures[:100], "warnings": warnings[:100], "blocks_publication": bool(failures),
        "final_export_self_validated": False, "canonical_order_self_validated": True,
        "precision_models_self_validated": True, "read_only": True,
    }


def _refresh_quality(report):
    sc = report.get("self_check") or {}; quality = report.setdefault("quality_gates", {})
    gates = [x for x in quality.get("gates") or [] if isinstance(x, dict) and x.get("key") != "report_self_check"]
    gates.append({
        "key": "report_self_check", "label": "Auto-contrôle précision du rapport",
        "status": "fail" if sc.get("failure_count") else ("warning" if sc.get("warning_count") else "pass"),
        "detail": f"{sc.get('pass_count',0)}/{sc.get('check_count',0)} contrôle(s) réussi(s) · {sc.get('warning_count',0)} avertissement(s) · {sc.get('failure_count',0)} échec(s)",
    })
    quality["gates"] = gates
    counts = {}
    for gate in gates:
        status = str(gate.get("status") or "pass"); counts[status] = counts.get(status, 0) + 1
    quality["counts"] = counts
    quality["overall"] = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")
    quality["non_pass_gates"] = [{k: x.get(k) for k in ("key", "label", "status", "detail")} for x in gates if x.get("status") != "pass"]


def _sync_trust(report):
    sc = report.get("self_check") or {}; trust = report.setdefault("doctor_view", {}).setdefault("trust", {})
    trust["self_check_status"] = sc.get("status"); trust["final_export_self_validated"] = bool(sc.get("final_export_self_validated"))
    if sc.get("failure_count"):
        trust["score"] = min(_int(trust.get("score"), 90), 50); trust["level"] = "low"
    elif _int(trust.get("score"), 90) >= 85:
        trust["level"] = "high"
    report["diagnostic_trust"] = trust


def run_self_check_v8(report):
    failures = []; warnings = []; checks = []

    def check(key, ok, severity="fail", detail=None):
        checks.append(key)
        if ok: return
        (failures if severity == "fail" else warnings).append({"key": key, "detail": detail or key})

    action = report.get("action_plan") or {}; actions = [x for x in action.get("items") or [] if isinstance(x, dict)]
    decision = report.get("decision_engine") or {}; decisions = [x for x in decision.get("items") or [] if isinstance(x, dict)]
    sem = report.get("condition_semantics") or {}; controller = report.get("controller_review_summary") or {}
    impact = report.get("controller_impact") or {}; temporal = report.get("temporal_analysis") or {}
    product = report.get("product_intelligence") or {}; truth = product.get("public_contract_truth") or {}
    doctor = report.get("doctor_view") or {}; perf = report.get("scan_performance") or {}; privacy = report.get("privacy") or {}
    findings = _finding_map(report); recs = report.get("resilience_recommendations") or {}
    duplicate = report.get("duplicate_action_semantics") or {}; feedback = report.get("automation_feedback_semantics") or {}

    # Current public identity.
    check("identity.version", report.get("version") == VERSION)
    check("identity.report_schema", (report.get("report_schema") or {}).get("version") == REPORT_SCHEMA)
    check("identity.share_schema", (report.get("share_contract") or {}).get("schema") == SHARE_SCHEMA)
    check("identity.share_model", (report.get("share_contract") or {}).get("model") == SHARE_MODEL)
    check("identity.action_model", action.get("model") == ACTION_PLAN_MODEL)
    check("identity.action_source", (report.get("diagnostic_summary") or {}).get("source") == ACTION_PLAN_SOURCE)
    check("identity.condition_model", sem.get("model") == CONDITION_MODEL)
    check("identity.controller_model", controller.get("model") == CONTROLLER_REVIEW_MODEL)
    check("identity.controller_impact_model", impact.get("model") == CONTROLLER_IMPACT_MODEL)
    check("identity.decision_model", decision.get("model") == DECISION_MODEL)
    check("identity.temporal_model", temporal.get("model") == TEMPORAL_MODEL)
    check("identity.history_contract", temporal.get("history_contract") == HISTORY_CONTRACT)
    check("identity.history_policy", temporal.get("history_policy") == HISTORY_POLICY)
    check("identity.publication_model", temporal.get("publication_model") == PUBLICATION_MODEL)
    check("identity.resilience_model", recs.get("analysis_model") == RESILIENCE_MODEL)
    check("identity.resilience_recommendation_model", recs.get("model") == RESILIENCE_RECOMMENDATION_MODEL)
    check("identity.duplicate_model", duplicate.get("model") == DUPLICATE_MODEL)
    check("identity.feedback_model", feedback.get("model") == LOOP_MODEL)
    check("identity.public_truth", all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity")) and bool(truth.get("canonical_order_identity")))

    # Acquisition / privacy invariants.
    check("acquisition.single_snapshot", perf.get("single_state_snapshot_preserved") is True)
    check("acquisition.no_extra_state_reads", _int(perf.get("additional_home_assistant_state_reads"), -1) == 0)
    check("acquisition.trust_sees_snapshot", (doctor.get("trust") or {}).get("single_snapshot_evidence") is True)
    check("privacy.no_auto_fix", doctor.get("automatic_fix") is False and report.get("automatic_fix", False) is False)
    check("privacy.read_only", (doctor.get("trust") or {}).get("read_only") is True)
    check("privacy.no_raw_states", not any(bool(privacy.get(k)) for k in ("v160_raw_states_persisted", "v150_raw_states_persisted", "v140_raw_states_persisted")))
    check("privacy.no_secret_values", not any(bool(privacy.get(k)) for k in ("v160_secret_values_persisted", "v150_secret_values_persisted", "v140_secret_values_persisted")))

    # Exact controller scope must equal the remaining physical pairs, not the historical graph.
    physical = [x for x in sem.get("unproven_pairs") or [] if isinstance(x, dict) and x.get("target_kind") == "actuator"]
    exact_automations = sorted({str(a) for pair in physical for a in pair.get("automations") or [] if a})
    exact_entities = sorted({str(pair.get("entity_id")) for pair in physical if pair.get("entity_id")})
    check("controller.exact_pair_count", _int(impact.get("physical_pair_count"), -1) == len(physical))
    check("controller.exact_automation_count", _int(impact.get("impacted_automation_count"), -1) == len(exact_automations))
    check("controller.exact_automations", list(impact.get("impacted_automations") or []) == exact_automations)
    check("controller.exact_entities", list(impact.get("target_entities") or []) == exact_entities)
    check("controller.scope", impact.get("scope") == "unresolved_physical_pairs_only")
    check("controller.no_broad_priority", impact.get("broad_historical_blast_radius_not_used_for_priority") is True)
    check("controller.summary_automation_count", _int(controller.get("exact_physical_automation_count"), -1) == len(exact_automations))

    # Action / decision identity and ONE canonical order.
    action_ids = [str(x.get("id")) for x in actions if x.get("id")]
    decision_ids = [str(x.get("id")) for x in decisions if x.get("id")]
    canonical = decision.get("canonical_order") or {}
    check("actions.total", _int(action.get("total"), -1) == len(actions))
    check("actions.unique", len(action_ids) == len(set(action_ids)) == len(actions))
    check("decision.total", _int(decision.get("total"), -1) == len(decisions) == len(actions))
    check("decision.ids", set(action_ids) == set(decision_ids))
    check("order.model", canonical.get("model") == CANONICAL_ORDER_MODEL)
    check("order.decision_identity", decision_ids == list(canonical.get("item_ids") or []))
    check("order.action_identity", action_ids == decision_ids)
    top_ids = [str(x.get("id")) for x in (report.get("diagnostic_summary") or {}).get("top_actions") or [] if x.get("id")]
    check("order.diagnostic_prefix", top_ids == decision_ids[:len(top_ids)])
    lanes = decision.get("lane_counts") or {}
    check("decision.lane_sum", sum(_int(v) for v in lanes.values()) == len(decisions))

    for idx, item in enumerate(decisions):
        pb = item.get("repair_playbook") or {}
        check(f"decision.{idx}.lane", item.get("operational_lane") in OPERATIONAL_LANES)
        check(f"decision.{idx}.readiness", pb.get("repair_readiness") in REPAIR_READINESS)
        check(f"decision.{idx}.playbook_model", pb.get("model") == REPAIR_PLAYBOOK_MODEL)
        check(f"decision.{idx}.steps", bool(pb.get("steps")))
        check(f"decision.{idx}.read_only", pb.get("automatic_fix") is False and pb.get("read_only") is True)
        if str(item.get("source_id") or "") == "HD-AUTO-003":
            dep = item.get("dependency_impact") or {}
            check(f"decision.{idx}.controller_scope", dep.get("scope") == "unresolved_physical_pairs_only")
            check(f"decision.{idx}.controller_count", _int(dep.get("impacted_automation_count"), -1) == len(exact_automations))
        if str(item.get("source_type") or "").startswith("registry_"):
            dep = item.get("dependency_impact") or {}
            if _int(dep.get("impacted_automation_count"), 0) == 0 and str(dep.get("level") or "none") not in {"high", "critical"}:
                check(f"registry.{idx}.watch", item.get("operational_lane") == "watch")

    # Resilience phase evidence cannot silently downgrade an unresolved pre-control risk.
    check("resilience.phase_parse", _int((report.get("resilience_precision") or {}).get("parse_error_count"), 0) == 0, "warning")
    for idx, rec in enumerate(recs.get("items") or []):
        if not isinstance(rec, dict): continue
        pre = _int(rec.get("pre_control_risk_count"), 0)
        if pre > 0:
            check(f"resilience.{idx}.pre_not_downgraded", rec.get("tier") == "must_fix")
        if rec.get("phase_adjustment") == "no_unprotected_pre_control_decision_proven":
            check(f"resilience.{idx}.downgrade_has_evidence", _int(rec.get("post_action_confirmation_count"), 0) + _int(rec.get("trigger_dependency_count"), 0) > 0)

    # Duplicate / feedback semantics are static classifications, not auto-fixes/runtime claims.
    check("duplicate.no_auto_cleanup", duplicate.get("automatic_cleanup") is False)
    for idx, item in enumerate(duplicate.get("items") or []):
        check(f"duplicate.{idx}.exact", item.get("exact_duplicate") is True)
        check(f"duplicate.{idx}.manual", item.get("automatic_removal_safe") is False)
    check("feedback.no_runtime_claim", _int(feedback.get("runtime_loop_proven_count"), 0) == 0)
    for idx, item in enumerate(feedback.get("items") or []):
        check(f"feedback.{idx}.not_runtime_proof", item.get("runtime_loop_proven") is False)

    # Source-derived counts still agree with findings.
    security = product.get("security") or {}; maintenance = product.get("maintenance") or {}
    check("source.security_active", _int(security.get("active_secret_hint_count"), 0) == finding_evidence_count(findings.get("HD-SEC-001") or {}))
    check("source.security_archive", _int(security.get("archive_secret_hint_count"), 0) == finding_evidence_count(findings.get("HD-SEC-003") or {}))
    check("source.missing_refs", _int(maintenance.get("missing_reference_count"), 0) == finding_evidence_count(findings.get("HD-CFG-001") or {}))

    # Temporal pre-commit truth plus visibility of the latest published baseline.
    check("temporal.publication_required", temporal.get("publication_complete_required_for_trust") is True)
    check("temporal.blocked_never_baseline", temporal.get("blocked_reports_never_become_score_baselines") is True)
    check("temporal.precommit_not_committed", temporal.get("current_committed_baseline") is not True)
    check("temporal.transaction_staged", (report.get("publication_transaction") or {}).get("phase") == "staged")
    check("temporal.baseline_visibility", temporal.get("baseline_visibility_independent_of_delta_eligibility") is True)

    # Install provisional self-check then validate the exact support payload containing it.
    result = _result(checks, failures, warnings); report["self_check"] = result
    share = build_share_report(report)
    check("share.built", isinstance(share, dict))
    if isinstance(share, dict):
        meta = share.get("export_meta") or {}; size = _int(meta.get("share_report_bytes_estimate"), 0)
        check("share.version", share.get("version") == VERSION)
        check("share.schema", (share.get("share_schema") or {}).get("version") == SHARE_SCHEMA)
        check("share.finding_identity", _int(meta.get("exported_finding_count"), -1) == len(report.get("findings") or []))
        check("share.action_identity", _int(meta.get("exported_action_count"), -1) == len(actions))
        check("share.target_bound", size <= SHARE_TARGET_BYTES, "warning", f"{size}>{SHARE_TARGET_BYTES}")
        check("share.hard_bound", size <= SHARE_HARD_BYTES, "fail", f"{size}>{SHARE_HARD_BYTES}")
        check("share.canonical_order", meta.get("canonical_order_preserved") is True)
        check("share.controller_scope", meta.get("controller_exact_scope_preserved") is True)
        check("share.privacy", meta.get("raw_states_included") is False and meta.get("raw_yaml_included") is False and meta.get("secret_values_included") is False)

    result = _result(checks, failures, warnings); result["final_export_self_validated"] = not bool(failures); report["self_check"] = result
    final_share = build_share_report(report)
    final_size = _int((final_share.get("export_meta") or {}).get("share_report_bytes_estimate"), 0) if isinstance(final_share, dict) else 0
    if final_size > SHARE_HARD_BYTES:
        failures.append({"key": "share.final_hard_bound", "detail": f"{final_size}>{SHARE_HARD_BYTES}"})
    elif final_size > SHARE_TARGET_BYTES:
        warnings.append({"key": "share.final_target_bound", "detail": f"{final_size}>{SHARE_TARGET_BYTES}"})
    result = _result(checks, failures, warnings)
    result["final_export_self_validated"] = not bool(failures); result["final_export_bytes"] = final_size
    report["self_check"] = result
    _refresh_quality(report); _sync_trust(report)
    report.setdefault("diagnostic_engine", {})["report_self_check_v8_precision_truth"] = True
    report.setdefault("privacy", {})["self_check_v8_additional_state_reads"] = 0
    return result


def post_commit_validation_v8(report):
    failures = []
    sc = report.get("self_check") or {}; tx = report.get("publication_transaction") or {}; temporal = report.get("temporal_analysis") or {}
    truth = (report.get("product_intelligence") or {}).get("public_contract_truth") or {}
    if sc.get("status") == "fail": failures.append({"key": "post_commit.self_check", "detail": "self_check_failed"})
    if tx.get("phase") != "committed" or tx.get("committed") is not True: failures.append({"key": "post_commit.transaction", "detail": str(tx)})
    if temporal.get("current_snapshot_publication_complete") is not True: failures.append({"key": "post_commit.temporal", "detail": "snapshot_not_published"})
    if temporal.get("current_committed_baseline") is not True: failures.append({"key": "post_commit.baseline_visibility", "detail": "committed_baseline_not_visible"})
    if not (all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity")) and bool(truth.get("canonical_order_identity"))):
        failures.append({"key": "post_commit.public_truth", "detail": str(truth)})
    share = build_share_report(report); size = _int((share.get("export_meta") or {}).get("share_report_bytes_estimate"), 0)
    if size > SHARE_HARD_BYTES: failures.append({"key": "post_commit.share_hard_bound", "detail": f"{size}>{SHARE_HARD_BYTES}"})
    if failures:
        existing = list(sc.get("failures") or []) + failures
        sc.update({"status": "fail", "blocks_publication": True, "failures": existing[:100], "failure_count": len(existing), "final_export_self_validated": False})
        report["self_check"] = sc; _refresh_quality(report); _sync_trust(report)
        return {"valid": False, "failures": failures}
    sc["publication_snapshot_self_validated"] = True; sc["post_commit_precision_validated"] = True
    report["self_check"] = sc; _refresh_quality(report); _sync_trust(report)
    return {"valid": True, "failures": []}
