"""HA Doctor 0.15 native final-export self-check.

The validator checks the current contract directly, installs a provisional
Self-Check into the report, then validates the *actual* Share V9 payload that
contains that Self-Check. A post-commit guard can still revoke publication if
final publication metadata makes the report inconsistent.
"""

from contracts_v150 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    SELF_CHECK_MODEL, CONDITION_MODEL, CONTROLLER_REVIEW_MODEL, ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE,
    DECISION_MODEL, REPAIR_PLAYBOOK_MODEL, TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY,
    PUBLICATION_MODEL, OPERATIONAL_LANES, REPAIR_READINESS,
)
from sharing_v150 import build_share_report
from product_v110 import finding_evidence_count


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def _finding_map(report):
    return {str(x.get("rule_id")): x for x in report.get("findings") or [] if isinstance(x, dict) and x.get("rule_id")}


def _refresh_quality(report):
    sc = report.get("self_check") or {}
    quality = report.setdefault("quality_gates", {})
    gates = [x for x in quality.get("gates") or [] if isinstance(x, dict) and x.get("key") != "report_self_check"]
    gates.append({
        "key": "report_self_check", "label": "Auto-contrôle final du rapport",
        "status": "fail" if sc.get("failure_count") else ("warning" if sc.get("warning_count") else "pass"),
        "detail": f"{sc.get('pass_count',0)}/{sc.get('check_count',0)} contrôle(s) réussi(s) · {sc.get('warning_count',0)} avertissement(s) · {sc.get('failure_count',0)} échec(s)",
    })
    quality["gates"] = gates
    counts = {}
    for gate in gates:
        status = str(gate.get("status") or "pass")
        counts[status] = counts.get(status, 0) + 1
    quality["counts"] = counts
    quality["overall"] = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")
    quality["non_pass_gates"] = [{k: x.get(k) for k in ("key", "label", "status", "detail")} for x in gates if x.get("status") != "pass"]


def _sync_trust(report):
    sc = report.get("self_check") or {}
    trust = report.setdefault("doctor_view", {}).setdefault("trust", {})
    trust["self_check_status"] = sc.get("status")
    trust["native_self_check"] = True
    trust["final_export_self_validated"] = bool(sc.get("final_export_self_validated"))
    if sc.get("failure_count"):
        trust["score"] = min(_int(trust.get("score"), 90), 50); trust["level"] = "low"
    elif _int(trust.get("score"), 90) >= 85:
        trust["level"] = "high"
    report["diagnostic_trust"] = trust


def _result(checks, failures, warnings):
    status = "fail" if failures else ("warning" if warnings else "pass")
    return {
        "model": SELF_CHECK_MODEL, "version": VERSION, "status": status,
        "check_count": len(checks), "pass_count": max(0, len(checks) - len(failures) - len(warnings)),
        "warning_count": len(warnings), "failure_count": len(failures),
        "failures": failures[:100], "warnings": warnings[:100], "blocks_publication": bool(failures),
        "native_current_contract_validation": True, "legacy_report_rewriting": False,
        "final_export_self_validated": False, "decision_engine_self_validated": True,
        "publication_transaction_self_validated": True, "read_only": True,
    }


def run_self_check_v7(report):
    failures = []; warnings = []; checks = []

    def check(key, ok, severity="fail", detail=None):
        checks.append(key)
        if ok:
            return
        (failures if severity == "fail" else warnings).append({"key": key, "detail": detail or key})

    action = report.get("action_plan") or {}; actions = [x for x in action.get("items") or [] if isinstance(x, dict)]
    decision = report.get("decision_engine") or {}; decisions = [x for x in decision.get("items") or [] if isinstance(x, dict)]
    sem = report.get("condition_semantics") or {}; temporal = report.get("temporal_analysis") or {}
    product = report.get("product_intelligence") or {}; truth = product.get("public_contract_truth") or {}
    controller = report.get("controller_review_summary") or {}; doctor = report.get("doctor_view") or {}
    findings = _finding_map(report); privacy = report.get("privacy") or {}; perf = report.get("scan_performance") or {}

    # Current public identity. No legacy rewriting is permitted.
    check("identity.version", report.get("version") == VERSION)
    check("identity.report_schema", (report.get("report_schema") or {}).get("version") == REPORT_SCHEMA)
    check("identity.share_schema", (report.get("share_contract") or {}).get("schema") == SHARE_SCHEMA)
    check("identity.share_model", (report.get("share_contract") or {}).get("model") == SHARE_MODEL)
    check("identity.action_model", action.get("model") == ACTION_PLAN_MODEL)
    check("identity.action_source", (report.get("diagnostic_summary") or {}).get("source") == ACTION_PLAN_SOURCE)
    check("identity.condition_model", sem.get("model") == CONDITION_MODEL)
    check("identity.controller_model", controller.get("model") == CONTROLLER_REVIEW_MODEL)
    check("identity.decision_model", decision.get("model") == DECISION_MODEL)
    check("identity.temporal_model", temporal.get("model") == TEMPORAL_MODEL)
    check("identity.history_contract", temporal.get("history_contract") == HISTORY_CONTRACT)
    check("identity.history_policy", temporal.get("history_policy") == HISTORY_POLICY)
    check("identity.publication_model", temporal.get("publication_model") == PUBLICATION_MODEL)
    check("identity.public_truth", all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity")))
    check("identity.truth_after_contract_install", truth.get("evaluated_after_contract_install") is True)

    # Acquisition evidence must already exist before product/trust computation.
    check("acquisition.single_snapshot", perf.get("single_state_snapshot_preserved") is True)
    check("acquisition.no_extra_state_reads", _int(perf.get("additional_home_assistant_state_reads"), -1) == 0)
    check("acquisition.trust_sees_snapshot", (doctor.get("trust") or {}).get("single_snapshot_evidence") is True)

    # Action/decision identities and operational summary.
    action_ids = [str(x.get("id")) for x in actions if x.get("id")]
    decision_ids = [str(x.get("id")) for x in decisions if x.get("id")]
    check("actions.total", _int(action.get("total"), len(actions)) == len(actions))
    check("actions.unique", len(action_ids) == len(set(action_ids)) == len(actions))
    check("decision.total", _int(decision.get("total"), -1) == len(decisions) == len(actions))
    check("decision.ids", set(decision_ids) == set(action_ids))
    lanes = decision.get("lane_counts") or {}
    check("decision.lane_sum", sum(_int(v) for v in lanes.values()) == len(decisions))
    summary = decision.get("operational_summary") or {}
    check("decision.summary_identity", all(_int(summary.get(k), -1) == _int(lanes.get(k), 0) for k in ("fix_now", "logic_review", "restore_if_needed", "watch", "optimize")))
    check("decision.headline_operational", "surveillance" in str((report.get("diagnostic_summary") or {}).get("headline") or "").lower())

    for idx, item in enumerate(decisions):
        pb = item.get("repair_playbook") or {}
        check(f"decision.{idx}.lane", item.get("operational_lane") in OPERATIONAL_LANES)
        check(f"decision.{idx}.readiness", pb.get("repair_readiness") in REPAIR_READINESS)
        check(f"decision.{idx}.playbook_model", pb.get("model") == REPAIR_PLAYBOOK_MODEL)
        check(f"decision.{idx}.steps", bool(pb.get("steps")))
        check(f"decision.{idx}.read_only", pb.get("automatic_fix") is False and pb.get("read_only") is True)
        if str(item.get("source_type") or "").startswith("registry_"):
            dep = item.get("dependency_impact") or {}
            if _int(dep.get("impacted_automation_count"), 0) == 0 and str(dep.get("level") or "none") not in {"high", "critical"}:
                check(f"registry.{idx}.watch", item.get("operational_lane") == "watch")

    # Event-aware controller evidence: never turn a static overlap into a runtime claim.
    event_pairs = 0
    for idx, pair in enumerate(sem.get("unproven_pairs") or []):
        if not isinstance(pair, dict):
            continue
        event = pair.get("v10_event_analysis") or {}
        if event.get("status") != "event_window_policy_overlap":
            continue
        event_pairs += 1
        check(f"event.{idx}.static", event.get("templates_executed") is False)
        check(f"event.{idx}.not_simultaneous", event.get("simultaneous_execution_proven") is False)
        check(f"event.{idx}.not_continuous", event.get("continuous_conflict_proven") is False)
        check(f"event.{idx}.conflicts", _int(event.get("conflict_path_pair_count"), 0) > 0)
        if _int(event.get("crossing_event_conflict_count"), 0) > 0:
            check(f"event.{idx}.crossing_semantics", event.get("numeric_state_crossing_semantics_applied") is True)
    check("event.count", event_pairs == _int(sem.get("event_window_policy_overlap_pair_count"), 0))

    # Source-derived counts remain truthful.
    security = product.get("security") or {}; maintenance = product.get("maintenance") or {}
    check("source.security_active", _int(security.get("active_secret_hint_count"), 0) == finding_evidence_count(findings.get("HD-SEC-001") or {}))
    check("source.security_archive", _int(security.get("archive_secret_hint_count"), 0) == finding_evidence_count(findings.get("HD-SEC-003") or {}))
    check("source.missing_refs", _int(maintenance.get("missing_reference_count"), 0) == finding_evidence_count(findings.get("HD-CFG-001") or {}))

    # Temporal preflight. Stage is not canonical yet.
    check("temporal.publication_required", temporal.get("publication_complete_required_for_trust") is True)
    check("temporal.blocked_never_baseline", temporal.get("blocked_reports_never_become_score_baselines") is True)
    check("temporal.precommit_not_canonical", temporal.get("current_snapshot_publication_complete") is not True)
    check("temporal.transaction_staged", (report.get("publication_transaction") or {}).get("phase") == "staged")

    # Privacy invariants.
    check("privacy.no_auto_fix", doctor.get("automatic_fix") is False and report.get("automatic_fix", False) is False)
    check("privacy.read_only", (doctor.get("trust") or {}).get("read_only") is True)
    check("privacy.no_raw_state_persistence", not any(bool(privacy.get(k)) for k in ("v150_raw_states_persisted", "v140_raw_states_persisted", "v130_raw_states_persisted")))
    check("privacy.no_secret_persistence", not any(bool(privacy.get(k)) for k in ("v150_secret_values_persisted", "v140_secret_values_persisted", "v130_secret_values_persisted")))

    # Install provisional Self-Check, then validate the real export that contains it.
    result = _result(checks, failures, warnings)
    report["self_check"] = result
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
        check("share.privacy", meta.get("raw_states_included") is False and meta.get("raw_yaml_included") is False and meta.get("secret_values_included") is False)

    result = _result(checks, failures, warnings)
    result["final_export_self_validated"] = not bool(failures)
    report["self_check"] = result

    # One final serialization with the final counts/status, not the provisional object.
    final_share = build_share_report(report)
    final_size = _int((final_share.get("export_meta") or {}).get("share_report_bytes_estimate"), 0) if isinstance(final_share, dict) else 0
    result["final_export_bytes"] = final_size
    if final_size > SHARE_HARD_BYTES:
        failures.append({"key": "share.final_hard_bound", "detail": f"{final_size}>{SHARE_HARD_BYTES}"})
    elif final_size > SHARE_TARGET_BYTES:
        warnings.append({"key": "share.final_target_bound", "detail": f"{final_size}>{SHARE_TARGET_BYTES}"})
    result = _result(checks, failures, warnings)
    result["final_export_self_validated"] = not bool(failures)
    result["final_export_bytes"] = final_size
    report["self_check"] = result
    _refresh_quality(report); _sync_trust(report)
    report.setdefault("diagnostic_engine", {})["report_self_check_v7_final_export"] = True
    report.setdefault("privacy", {})["self_check_v7_additional_state_reads"] = 0
    return result


def post_commit_validation(report):
    """Validate the final report after canonical publication metadata is attached."""
    failures = []
    sc = report.get("self_check") or {}; tx = report.get("publication_transaction") or {}
    truth = (report.get("product_intelligence") or {}).get("public_contract_truth") or {}
    if sc.get("status") == "fail":
        failures.append({"key": "post_commit.preexisting_self_check_failure", "detail": "self_check_not_passable"})
    if tx.get("phase") != "committed" or tx.get("committed") is not True:
        failures.append({"key": "post_commit.transaction", "detail": str(tx)})
    if (report.get("temporal_analysis") or {}).get("current_snapshot_publication_complete") is not True:
        failures.append({"key": "post_commit.temporal_publication", "detail": "current_snapshot_not_published"})
    if not (all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity"))):
        failures.append({"key": "post_commit.public_truth", "detail": str(truth)})
    share = build_share_report(report)
    size = _int((share.get("export_meta") or {}).get("share_report_bytes_estimate"), 0) if isinstance(share, dict) else 0
    if size > SHARE_HARD_BYTES:
        failures.append({"key": "post_commit.share_hard_bound", "detail": f"{size}>{SHARE_HARD_BYTES}"})

    if failures:
        existing = list(sc.get("failures") or []) + failures
        sc.update({
            "status": "fail", "blocks_publication": True, "failures": existing[:100],
            "failure_count": len(existing), "final_export_self_validated": False,
            "post_commit_validation": "fail", "final_export_bytes": size,
        })
        sc["check_count"] = _int(sc.get("check_count"), 0) + len(failures)
        sc["pass_count"] = max(0, _int(sc.get("check_count"), 0) - _int(sc.get("failure_count"), 0) - _int(sc.get("warning_count"), 0))
    else:
        sc["post_commit_validation"] = "pass"
        sc["final_export_bytes"] = size
    report["self_check"] = sc
    _refresh_quality(report); _sync_trust(report)
    return {"valid": not failures, "failures": failures, "share_bytes": size}
