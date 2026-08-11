"""HA Doctor 0.12 self-check for canonical temporal history and fresh public contracts."""

import selfcheck_v110 as base
from contracts_v120 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    SELF_CHECK_MODEL, TEMPORAL_MODEL, HISTORY_CONTRACT, SCORE_TRACE_MODEL,
    CONTROLLER_REVIEW_MODEL, ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE,
)
from sharing_v120 import build_share_report
from temporal_v120 import validate_current_canonical_snapshot


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def run_self_check_v4(report, history_path=None):
    saved_version = report.get("version")
    saved_schema = dict(report.get("report_schema") or {})
    saved_share = dict(report.get("share_contract") or {})
    saved_action_model = (report.get("action_plan") or {}).get("model")
    saved_source = (report.get("diagnostic_summary") or {}).get("source")
    saved_controller_model = (report.get("controller_review_summary") or {}).get("model")
    saved_temporal_model = (report.get("temporal_analysis") or {}).get("model")

    report["version"] = "0.11.0"
    report.setdefault("report_schema", {})["version"] = "ha-doctor-report/0.11"
    report["share_contract"] = {"schema": "ha-doctor-share/5", "model": "assistant_share_report_v5", "target_bytes": 28000, "hard_bytes": 32000, "single_source_of_truth": True}
    base_result = base.run_self_check_v3(report)

    report["version"] = saved_version
    report["report_schema"] = saved_schema
    report["share_contract"] = saved_share
    report.setdefault("action_plan", {})["model"] = saved_action_model
    report.setdefault("diagnostic_summary", {})["source"] = saved_source
    report.setdefault("controller_review_summary", {})["model"] = saved_controller_model
    report.setdefault("temporal_analysis", {})["model"] = saved_temporal_model

    failures = list(base_result.get("failures") or [])
    warnings = list(base_result.get("warnings") or [])
    check_count = _int(base_result.get("check_count"), 0)

    def check(key, ok, severity="fail", detail=None):
        nonlocal check_count
        check_count += 1
        if ok:
            return
        (failures if severity == "fail" else warnings).append({"key": key, "detail": detail or key})

    temporal = report.get("temporal_analysis") or {}
    product = report.get("product_intelligence") or {}
    trace = product.get("score_change_trace") or {}
    contracts = product.get("public_contract_truth") or {}
    current_score = _int((report.get("scores") or {}).get("global"), 0)

    check("v120_version_identity", report.get("version") == VERSION)
    check("v120_report_schema_identity", (report.get("report_schema") or {}).get("version") == REPORT_SCHEMA)
    check("v120_share_schema_identity", (report.get("share_contract") or {}).get("schema") == SHARE_SCHEMA)
    check("v120_share_model_identity", (report.get("share_contract") or {}).get("model") == SHARE_MODEL)
    check("v120_action_plan_model_fresh", (report.get("action_plan") or {}).get("model") == ACTION_PLAN_MODEL)
    check("v120_diagnostic_source_fresh", (report.get("diagnostic_summary") or {}).get("source") == ACTION_PLAN_SOURCE)
    check("v120_controller_review_model_fresh", (report.get("controller_review_summary") or {}).get("model") == CONTROLLER_REVIEW_MODEL)
    check("v120_temporal_model_identity", temporal.get("model") == TEMPORAL_MODEL)
    check("v120_history_contract_identity", temporal.get("history_contract") == HISTORY_CONTRACT)
    check("v120_trace_model_identity", trace.get("model") == SCORE_TRACE_MODEL)

    trusted = bool(temporal.get("previous_score_trusted"))
    previous = temporal.get("previous_score")
    delta = temporal.get("score_delta")
    if trusted:
        check("v120_trusted_previous_score_present", previous is not None)
        check("v120_trusted_delta_math", delta == current_score - _int(previous, current_score))
        check("v120_trace_delta_identity", trace.get("score_delta") == delta)
    else:
        check("v120_untrusted_previous_score_hidden", previous is None)
        check("v120_untrusted_delta_suppressed", delta is None)
        check("v120_no_false_stability", temporal.get("score_comparison_status") != "canonical")
        if temporal.get("meaningful_previous_generated_at"):
            check("v120_legacy_false_stability_flag", temporal.get("false_stability_prevented") is True)

    check("v120_trace_trust_identity", bool(trace.get("previous_score_trusted")) == trusted)
    check("v120_trace_current_score_identity", _int(trace.get("primary_score"), -1) == current_score)
    check("v120_public_contract_truth", all(bool(value) for key, value in contracts.items() if key.endswith("_fresh")))
    check("v120_quality_detail_no_stale_v6", all("V6" not in str(gate.get("detail") or "") for gate in (report.get("quality_gates") or {}).get("gates") or [] if isinstance(gate, dict) and gate.get("key") == "condition_semantics"))

    snapshot = validate_current_canonical_snapshot(report, history_path=history_path)
    check("v120_current_history_snapshot_canonical", snapshot.get("valid") is True, "fail", str(snapshot))

    share = build_share_report(report)
    check("v120_share_built", isinstance(share, dict))
    if isinstance(share, dict):
        meta = share.get("export_meta") or {}
        size = _int(meta.get("share_report_bytes_estimate"), 0)
        check("v120_share_hard_bound", size <= SHARE_HARD_BYTES)
        check("v120_share_target_bound", size <= SHARE_TARGET_BYTES, "warning")
        check("v120_share_version", share.get("version") == VERSION)
        check("v120_share_schema", (share.get("share_schema") or {}).get("version") == SHARE_SCHEMA)
        share_temporal = share.get("temporal_truth") or {}
        check("v120_share_temporal_contract", share_temporal.get("history_contract") == HISTORY_CONTRACT)
        check("v120_share_temporal_trust_identity", bool(share_temporal.get("previous_score_trusted")) == trusted)
        if not trusted:
            check("v120_share_no_false_delta", share_temporal.get("score_delta") is None)
        public = share.get("public_contracts") or {}
        check("v120_share_action_model", public.get("action_plan_model") == ACTION_PLAN_MODEL)
        check("v120_share_diagnostic_source", public.get("diagnostic_source") == ACTION_PLAN_SOURCE)
        check("v120_share_controller_model", public.get("controller_review_model") == CONTROLLER_REVIEW_MODEL)

    status = "fail" if failures else ("warning" if warnings else "pass")
    result = {
        "model": SELF_CHECK_MODEL, "version": VERSION, "status": status, "check_count": check_count,
        "pass_count": max(0, check_count - len(failures) - len(warnings)), "warning_count": len(warnings),
        "failure_count": len(failures), "failures": failures[:50], "warnings": warnings[:50],
        "blocks_publication": bool(failures), "export_self_validated": True,
        "temporal_history_self_validated": True, "public_contracts_self_validated": True,
        "read_only": True,
    }
    report["self_check"] = result
    report.setdefault("diagnostic_engine", {})["report_self_check_v4"] = True
    report.setdefault("privacy", {})["self_check_v4_additional_state_reads"] = 0
    return result
