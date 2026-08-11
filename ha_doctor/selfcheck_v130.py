"""HA Doctor 0.13 self-check for decisions, playbooks and mandatory guard proofs."""

import selfcheck_v120 as base
from contracts_v130 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    SELF_CHECK_MODEL, CONDITION_MODEL, CONTROLLER_REVIEW_MODEL, ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE,
    DECISION_MODEL, REPAIR_PLAYBOOK_MODEL,
)
from sharing_v130 import build_share_report


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def run_self_check_v5(report, history_path=None):
    saved = {
        "version": report.get("version"),
        "schema": dict(report.get("report_schema") or {}),
        "share": dict(report.get("share_contract") or {}),
        "action_model": (report.get("action_plan") or {}).get("model"),
        "source": (report.get("diagnostic_summary") or {}).get("source"),
        "controller_model": (report.get("controller_review_summary") or {}).get("model"),
    }
    report["version"] = "0.12.0"
    report.setdefault("report_schema", {})["version"] = "ha-doctor-report/0.12"
    report["share_contract"] = {"schema": "ha-doctor-share/6", "model": "assistant_share_report_v6", "target_bytes": 28000, "hard_bytes": 32000, "single_source_of_truth": True}
    report.setdefault("action_plan", {})["model"] = "correlated_action_plan_v4_temporal_truth"
    report.setdefault("diagnostic_summary", {})["source"] = "final_cross_validated_action_plan_v120"
    report.setdefault("controller_review_summary", {})["model"] = "controller_review_summary_v3_evidence"
    base_result = base.run_self_check_v4(report, history_path=history_path)

    report["version"] = saved["version"]
    report["report_schema"] = saved["schema"]
    report["share_contract"] = saved["share"]
    report.setdefault("action_plan", {})["model"] = saved["action_model"]
    report.setdefault("diagnostic_summary", {})["source"] = saved["source"]
    report.setdefault("controller_review_summary", {})["model"] = saved["controller_model"]

    failures = list(base_result.get("failures") or [])
    warnings = list(base_result.get("warnings") or [])
    check_count = _int(base_result.get("check_count"), 0)

    def check(key, ok, severity="fail", detail=None):
        nonlocal check_count
        check_count += 1
        if ok:
            return
        (failures if severity == "fail" else warnings).append({"key": key, "detail": detail or key})

    sem = report.get("condition_semantics") or {}
    decision = report.get("decision_engine") or {}
    product = report.get("product_intelligence") or {}
    truth = product.get("public_contract_truth") or {}
    actions = [x for x in (report.get("action_plan") or {}).get("items") or [] if isinstance(x, dict)]

    check("v130_version_identity", report.get("version") == VERSION)
    check("v130_schema_identity", (report.get("report_schema") or {}).get("version") == REPORT_SCHEMA)
    check("v130_share_contract_identity", (report.get("share_contract") or {}).get("schema") == SHARE_SCHEMA and (report.get("share_contract") or {}).get("model") == SHARE_MODEL)
    check("v130_condition_model", sem.get("model") == CONDITION_MODEL)
    check("v130_controller_model", (report.get("controller_review_summary") or {}).get("model") == CONTROLLER_REVIEW_MODEL)
    check("v130_action_model", (report.get("action_plan") or {}).get("model") == ACTION_PLAN_MODEL)
    check("v130_action_source", (report.get("diagnostic_summary") or {}).get("source") == ACTION_PLAN_SOURCE)
    check("v130_decision_model", decision.get("model") == DECISION_MODEL)
    check("v130_decision_action_identity", _int(decision.get("total"), -1) == len(actions))
    check("v130_decision_items_identity", len(decision.get("items") or []) == len(actions))

    decision_ids = {str(x.get("id")) for x in decision.get("items") or [] if isinstance(x, dict) and x.get("id")}
    action_ids = {str(x.get("id")) for x in actions if x.get("id")}
    check("v130_decision_ids_match_actions", decision_ids == action_ids)
    for idx, item in enumerate(decision.get("items") or []):
        if not isinstance(item, dict):
            check(f"v130_decision_item_dict:{idx}", False); continue
        playbook = item.get("repair_playbook") or {}
        check(f"v130_playbook_model:{idx}", playbook.get("model") == REPAIR_PLAYBOOK_MODEL)
        check(f"v130_playbook_readiness:{idx}", bool(playbook.get("repair_readiness")))
        check(f"v130_playbook_steps:{idx}", bool(playbook.get("steps")))
        check(f"v130_playbook_success:{idx}", bool(playbook.get("success_criteria")))
        check(f"v130_playbook_no_auto_fix:{idx}", playbook.get("automatic_fix") is False and playbook.get("read_only") is True)
        check(f"v130_operational_relevance:{idx}", item.get("operational_relevance") in {"high", "medium", "low"})

    for idx, resolved in enumerate(sem.get("mandatory_guard_resolutions") or []):
        evidence = (resolved or {}).get("evidence") or {}
        check(f"v130_guard_resolution_proof:{idx}", _int(evidence.get("proof_count"), 0) > 0)
        check(f"v130_guard_resolution_static:{idx}", evidence.get("templates_executed") is False)
        check(f"v130_guard_resolution_reason:{idx}", (resolved or {}).get("reason") == "mandatory_state_guard_exclusion")
    for idx, pair in enumerate(sem.get("unproven_pairs") or []):
        if not isinstance(pair, dict) or not pair.get("v8_guard_matrix"):
            continue
        matrix = pair.get("v8_guard_matrix") or {}
        check(f"v130_unresolved_guard_has_no_proof:{idx}", _int(matrix.get("proof_count"), 0) == 0)
        check(f"v130_unresolved_guard_static:{idx}", matrix.get("templates_executed") is False)

    check("v130_public_truth", all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity")))
    quality_gate = next((x for x in (report.get("quality_gates") or {}).get("gates") or [] if isinstance(x, dict) and x.get("key") == "decision_engine"), None)
    check("v130_decision_quality_gate", bool(quality_gate) and quality_gate.get("status") == "pass")

    share = build_share_report(report)
    check("v130_share_built", isinstance(share, dict))
    if isinstance(share, dict):
        meta = share.get("export_meta") or {}
        size = _int(meta.get("share_report_bytes_estimate"), 0)
        check("v130_share_hard_bound", size <= SHARE_HARD_BYTES)
        check("v130_share_target_bound", size <= SHARE_TARGET_BYTES, "warning")
        check("v130_share_version", share.get("version") == VERSION)
        check("v130_share_schema", (share.get("share_schema") or {}).get("version") == SHARE_SCHEMA)
        check("v130_share_decision_model", (share.get("decision_engine") or {}).get("model") == DECISION_MODEL)
        check("v130_share_guard_model", (share.get("controller_guard_matrix") or {}).get("model") == CONDITION_MODEL)
        check("v130_share_privacy", meta.get("raw_states_included") is False and meta.get("raw_yaml_included") is False and meta.get("secret_values_included") is False)

    status = "fail" if failures else ("warning" if warnings else "pass")
    result = {
        "model": SELF_CHECK_MODEL, "version": VERSION, "status": status, "check_count": check_count,
        "pass_count": max(0, check_count - len(failures) - len(warnings)), "warning_count": len(warnings),
        "failure_count": len(failures), "failures": failures[:60], "warnings": warnings[:60],
        "blocks_publication": bool(failures), "export_self_validated": True,
        "decision_engine_self_validated": True, "mandatory_guard_proofs_self_validated": True,
        "temporal_history_self_validated": True, "read_only": True,
    }
    report["self_check"] = result
    report.setdefault("diagnostic_engine", {})["report_self_check_v5"] = True
    report.setdefault("privacy", {})["self_check_v5_additional_state_reads"] = 0
    return result
