"""HA Doctor 0.14 native self-check.

Unlike 0.12/0.13, this validator never rewrites the current report into an old
version to replay legacy checks. It validates the current public contracts,
cross-section counts, decision items, controller evidence, temporal trust,
privacy and the actual Share V8 payload directly.
"""

from contracts_v140 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    SELF_CHECK_MODEL, CONDITION_MODEL, CONTROLLER_REVIEW_MODEL, ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE,
    DECISION_MODEL, REPAIR_PLAYBOOK_MODEL, TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY,
    OPERATIONAL_LANES, REPAIR_READINESS,
)
from sharing_v140 import build_share_report
from product_v110 import finding_evidence_count


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def _finding_map(report):
    return {str(x.get("rule_id")): x for x in report.get("findings") or [] if isinstance(x, dict) and x.get("rule_id")}


def run_self_check_v6(report):
    failures = []; warnings = []; checks = []

    def check(key, ok, severity="fail", detail=None):
        checks.append(key)
        if ok: return
        target = failures if severity == "fail" else warnings
        target.append({"key": key, "detail": detail or key})

    action = report.get("action_plan") or {}; actions = [x for x in action.get("items") or [] if isinstance(x, dict)]
    decision = report.get("decision_engine") or {}; decisions = [x for x in decision.get("items") or [] if isinstance(x, dict)]
    sem = report.get("condition_semantics") or {}; temporal = report.get("temporal_analysis") or {}
    product = report.get("product_intelligence") or {}; truth = product.get("public_contract_truth") or {}
    controller = report.get("controller_review_summary") or {}; doctor = report.get("doctor_view") or {}
    findings = _finding_map(report); privacy = report.get("privacy") or {}; flow = report.get("flow_confidence") or {}

    # Public identities and single-source contracts.
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
    check("identity.public_truth", all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity")))

    # Action-plan arithmetic and identities.
    action_ids = [str(x.get("id")) for x in actions if x.get("id")]
    decision_ids = [str(x.get("id")) for x in decisions if x.get("id")]
    check("actions.total", _int(action.get("total"), len(actions)) == len(actions))
    check("actions.plan_id_count", _int((report.get("diagnostic_summary") or {}).get("plan_id_count"), -1) == len(actions))
    check("actions.unique_ids", len(action_ids) == len(set(action_ids)) == len(actions))
    check("actions.counts_sum", sum(_int(v) for v in (action.get("counts") or {}).values()) == len(actions))
    check("decision.total", _int(decision.get("total"), -1) == len(decisions) == len(actions))
    check("decision.ids_match", set(decision_ids) == set(action_ids))
    check("decision.unique_ids", len(decision_ids) == len(set(decision_ids)))

    for idx, item in enumerate(decisions):
        pb = item.get("repair_playbook") or {}
        check(f"decision.{idx}.lane", item.get("operational_lane") in OPERATIONAL_LANES)
        check(f"decision.{idx}.relevance", item.get("operational_relevance") in {"high", "medium", "low"})
        check(f"decision.{idx}.priority_score", 0 <= _int(item.get("execution_priority_score"), -1) <= 100)
        check(f"decision.{idx}.playbook_model", pb.get("model") == REPAIR_PLAYBOOK_MODEL)
        check(f"decision.{idx}.readiness", pb.get("repair_readiness") in REPAIR_READINESS)
        check(f"decision.{idx}.steps", bool(pb.get("steps")))
        check(f"decision.{idx}.success", bool(pb.get("success_criteria")))
        check(f"decision.{idx}.read_only", pb.get("automatic_fix") is False and pb.get("read_only") is True)

    # Zero-blast registry incidents belong to watch, not primary logic review.
    for idx, item in enumerate(decisions):
        if not str(item.get("source_type") or "").startswith("registry_"): continue
        dep = item.get("dependency_impact") or {}; impacted = _int(dep.get("impacted_automation_count"), 0)
        if impacted == 0 and str(dep.get("level") or "none") not in {"high", "critical"}:
            check(f"registry.{idx}.zero_impact_watch", item.get("operational_lane") == "watch")
            check(f"registry.{idx}.zero_impact_low", item.get("operational_relevance") == "low")

    # Controller proof semantics.
    check("controller.count_identity", _int(controller.get("pair_count"), -1) == _int(sem.get("unproven_pair_count"), 0))
    check("controller.physical_identity", _int(controller.get("physical_pair_count"), -1) == _int(sem.get("physical_unproven_pair_count"), 0))
    check("controller.helper_identity", _int(controller.get("helper_pair_count"), -1) == _int(sem.get("helper_unproven_pair_count"), 0))
    for idx, resolved in enumerate(sem.get("branch_numeric_resolutions") or []):
        ev = (resolved or {}).get("evidence") or {}
        check(f"controller.numeric_resolution.{idx}.status", ev.get("status") == "numeric_exclusion")
        check(f"controller.numeric_resolution.{idx}.opposing_paths", _int(ev.get("opposing_path_pair_count"), 0) > 0)
        check(f"controller.numeric_resolution.{idx}.no_conflicts", _int(ev.get("conflict_path_pair_count"), 0) == 0)
        check(f"controller.numeric_resolution.{idx}.static", ev.get("templates_executed") is False)
    policy_pairs = 0
    for idx, pair in enumerate(sem.get("unproven_pairs") or []):
        if not isinstance(pair, dict): continue
        analysis = pair.get("v9_policy_analysis") or {}
        if analysis.get("status") == "policy_overlap":
            policy_pairs += 1
            check(f"controller.policy.{idx}.conflict", _int(analysis.get("conflict_path_pair_count"), 0) > 0)
            check(f"controller.policy.{idx}.not_runtime_claim", analysis.get("simultaneous_execution_proven") is False)
            check(f"controller.policy.{idx}.static", analysis.get("templates_executed") is False)
    check("controller.policy_count", policy_pairs == _int(sem.get("policy_overlap_pair_count"), 0))

    # Source-derived security and maintenance truth.
    security = product.get("security") or {}; maintenance = product.get("maintenance") or {}
    check("source.security_active", _int(security.get("active_secret_hint_count"), 0) == finding_evidence_count(findings.get("HD-SEC-001") or {}))
    check("source.security_archive", _int(security.get("archive_secret_hint_count"), 0) == finding_evidence_count(findings.get("HD-SEC-003") or {}))
    check("source.missing_refs", _int(maintenance.get("missing_reference_count"), 0) == finding_evidence_count(findings.get("HD-CFG-001") or {}))
    check("source.local_unavailable", _int(maintenance.get("local_unavailable_review"), 0) == finding_evidence_count(findings.get("HD-REG-002") or {}))

    # Temporal score trust. Unpublished/blocked snapshots are never accepted.
    trusted = bool(temporal.get("previous_score_trusted")); previous = temporal.get("previous_score"); delta = temporal.get("score_delta")
    current = _int((report.get("scores") or {}).get("global"), 0)
    if trusted:
        check("temporal.trusted_status", temporal.get("score_comparison_status") == "canonical")
        check("temporal.trusted_previous", previous is not None)
        check("temporal.trusted_math", delta == current - _int(previous, current))
    else:
        check("temporal.untrusted_previous_hidden", previous is None)
        check("temporal.untrusted_delta_hidden", delta is None)
        check("temporal.untrusted_not_canonical", temporal.get("score_comparison_status") != "canonical")
    check("temporal.publication_required", temporal.get("publication_complete_required_for_trust") is True)
    check("temporal.blocked_never_baseline", temporal.get("blocked_reports_never_become_score_baselines") is True)

    # Acquisition and privacy invariants.
    perf = report.get("scan_performance") or {}
    check("acquisition.single_snapshot", bool(perf.get("single_state_snapshot_preserved") or privacy.get("single_ephemeral_state_snapshot") or privacy.get("state_snapshot_ephemeral")))
    check("acquisition.no_extra_state_reads", _int(perf.get("additional_home_assistant_state_reads"), 0) == 0)
    check("privacy.no_auto_fix", doctor.get("automatic_fix") is False and report.get("automatic_fix", False) is False)
    check("privacy.read_only_trust", (doctor.get("trust") or {}).get("read_only") is True)
    check("privacy.no_raw_state_persistence", not any(bool(privacy.get(k)) for k in ("v140_raw_states_persisted", "v130_raw_states_persisted", "v120_raw_states_persisted")))
    check("privacy.no_secret_persistence", not any(bool(privacy.get(k)) for k in ("v140_secret_values_persisted", "v130_secret_values_persisted", "v120_secret_values_persisted")))

    # Flow/consistency fundamentals.
    check("flow.resolution", float(flow.get("target_resolution_rate", 0) or 0) >= 0.99)
    check("flow.unresolved_dynamic", _int(flow.get("unresolved_dynamic_targets"), 0) == 0)
    check("flow.review_dynamic", _int(flow.get("review_required_dynamic_edges"), 0) == 0)
    consistency = report.get("consistency") or report.get("consistency_gates") or {}
    check("consistency.no_failure", _int(consistency.get("failure_count"), 0) == 0 and consistency.get("status", "pass") != "fail")

    # No stale generation labels in public summaries.
    executive_text = str((report.get("executive_summary") or {}).get("text") or "")
    check("public.executive_v9", "Contrôleurs V9" in executive_text)
    check("public.no_stale_controller_labels", "Contrôleurs V7" not in executive_text and "Contrôleurs V8" not in executive_text)
    check("public.no_stale_action_source", "v087" not in str((report.get("diagnostic_summary") or {}).get("source") or ""))

    # Validate the actual support export, not an approximation.
    share = build_share_report(report)
    check("share.built", isinstance(share, dict))
    if isinstance(share, dict):
        meta = share.get("export_meta") or {}; size = _int(meta.get("share_report_bytes_estimate"), 0)
        check("share.version", share.get("version") == VERSION)
        check("share.schema", (share.get("share_schema") or {}).get("version") == SHARE_SCHEMA)
        check("share.target_bound", size <= SHARE_TARGET_BYTES, "warning", f"{size}>{SHARE_TARGET_BYTES}")
        check("share.hard_bound", size <= SHARE_HARD_BYTES, "fail", f"{size}>{SHARE_HARD_BYTES}")
        check("share.finding_identity", _int(meta.get("exported_finding_count"), -1) == len(report.get("findings") or []))
        check("share.action_identity", _int(meta.get("exported_action_count"), -1) == len(actions))
        check("share.decision_model", (share.get("decision_engine") or {}).get("model") == DECISION_MODEL)
        check("share.condition_model", (share.get("condition_semantics") or {}).get("model") == CONDITION_MODEL)
        check("share.temporal_policy", (share.get("temporal_truth") or {}).get("history_policy") == HISTORY_POLICY)
        check("share.privacy", meta.get("raw_states_included") is False and meta.get("raw_yaml_included") is False and meta.get("secret_values_included") is False)
        if policy_pairs:
            review_items = (share.get("condition_semantics") or {}).get("review_items") or []
            check("share.policy_evidence", any(((x.get("policy_analysis") or {}).get("status") == "policy_overlap") for x in review_items if isinstance(x, dict)))

    status = "fail" if failures else ("warning" if warnings else "pass")
    result = {
        "model": SELF_CHECK_MODEL, "version": VERSION, "status": status,
        "check_count": len(checks), "pass_count": max(0, len(checks) - len(failures) - len(warnings)),
        "warning_count": len(warnings), "failure_count": len(failures),
        "failures": failures[:80], "warnings": warnings[:80], "blocks_publication": bool(failures),
        "native_current_contract_validation": True, "legacy_report_rewriting": False,
        "export_self_validated": True, "decision_engine_self_validated": True,
        "publication_aware_temporal_self_validated": True, "read_only": True,
    }
    report["self_check"] = result

    quality = report.setdefault("quality_gates", {})
    gates = [x for x in quality.get("gates") or [] if isinstance(x, dict) and x.get("key") != "report_self_check"]
    gates.append({
        "key": "report_self_check", "label": "Auto-contrôle natif du rapport",
        "status": "fail" if failures else ("warning" if warnings else "pass"),
        "detail": f"{result['pass_count']}/{result['check_count']} contrôle(s) réussi(s) · {len(warnings)} avertissement(s) · {len(failures)} échec(s)",
    })
    quality["gates"] = gates
    counts = {}
    for gate in gates: counts[str(gate.get("status") or "pass")] = counts.get(str(gate.get("status") or "pass"), 0) + 1
    quality["counts"] = counts
    quality["overall"] = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")
    quality["non_pass_gates"] = [{k: x.get(k) for k in ("key", "label", "status", "detail")} for x in gates if x.get("status") != "pass"]

    trust = report.setdefault("doctor_view", {}).setdefault("trust", {})
    trust["model"] = "diagnostic_trust_v6_native_self_check"
    trust["self_check_status"] = status; trust["native_self_check"] = True
    if failures: trust["score"] = min(_int(trust.get("score"), 90), 50); trust["level"] = "low"
    report["diagnostic_trust"] = trust
    report.setdefault("diagnostic_engine", {})["report_self_check_v6_native"] = True
    report.setdefault("privacy", {})["self_check_v6_additional_state_reads"] = 0
    return result
