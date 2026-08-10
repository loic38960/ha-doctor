"""Cross-contract self-check for HA Doctor 0.10 Engine Candidate."""

import json
from collections import Counter

from contracts_v100 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES,
    SHARE_HARD_BYTES, SELF_CHECK_MODEL, VERDICT_CODES, EVIDENCE_LEVELS,
)


def _int(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return int(default)


def _float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def run_self_check_v2(report):
    failures = []
    warnings = []
    check_count = 0

    def check(key, ok, severity="fail", detail=None):
        nonlocal check_count
        check_count += 1
        if ok:
            return
        target = failures if severity == "fail" else warnings
        target.append({"key": key, "detail": detail or key})

    if not isinstance(report, dict):
        return {
            "model": SELF_CHECK_MODEL, "version": VERSION, "status": "fail",
            "check_count": 1, "pass_count": 0, "warning_count": 0,
            "failure_count": 1, "failures": [{"key": "report_type", "detail": "Rapport non objet."}],
            "warnings": [], "blocks_publication": True,
        }

    findings = [x for x in report.get("findings") or [] if isinstance(x, dict)]
    plan = report.get("action_plan") or {}
    actions = [x for x in plan.get("items") or [] if isinstance(x, dict)]
    triage = report.get("triage_board") or {}
    triage_items = [x for x in triage.get("items") or [] if isinstance(x, dict)]
    doctor = report.get("doctor_view") or {}
    scores = report.get("scores") or {}
    severity_counts = report.get("severity_counts") or {}
    schema = report.get("report_schema") or {}
    share = report.get("share_contract") or {}
    sem = report.get("condition_semantics") or {}
    resilience = report.get("resilience_analysis") or {}
    recs = report.get("resilience_recommendations") or {}
    flow = report.get("flow_confidence") or {}
    temporal = report.get("temporal_analysis") or {}
    privacy = report.get("privacy") or {}
    product = report.get("product_intelligence") or {}
    inventory = report.get("inventory") or report.get("inventory_summary") or {}

    check("product_identity", str(report.get("product") or "HA Doctor") == "HA Doctor")
    check("version_identity", str(report.get("version") or "") == VERSION)
    check("report_schema_identity", str(schema.get("version") or "") == REPORT_SCHEMA)
    check("generated_at_present", bool(report.get("generated_at")))
    check("global_score_bounds", 0 <= _float(scores.get("global"), -1) <= 100)
    for domain, value in (scores.get("domains") or {}).items():
        check(f"domain_score_bounds:{domain}", 0 <= _float(value, -1) <= 100)

    actual_severity = Counter(str(x.get("severity") or "info") for x in findings)
    for key in ("critical", "high", "medium", "low", "info"):
        check(f"severity_count:{key}", _int(severity_counts.get(key)) == actual_severity.get(key, 0), "warning")

    finding_ids = [str(x.get("rule_id")) for x in findings if x.get("rule_id")]
    action_ids = [str(x.get("id")) for x in actions if x.get("id")]
    triage_ids = [str(x.get("id")) for x in triage_items if x.get("id")]
    check("finding_ids_unique", len(finding_ids) == len(set(finding_ids)))
    check("action_ids_complete", len(action_ids) == len(actions))
    check("action_ids_unique", len(action_ids) == len(set(action_ids)))
    check("plan_total_identity", _int(plan.get("total"), len(actions)) == len(actions))
    expected_priority = Counter(str(x.get("priority") or "info") for x in actions)
    for key in ("action_now", "verify", "optimize"):
        check(f"plan_priority:{key}", _int((plan.get("counts") or {}).get(key)) == expected_priority.get(key, 0))
    check("triage_total_identity", _int(triage.get("total"), len(triage_items)) == len(actions))
    check("triage_action_identity", set(triage_ids) == set(action_ids))

    check("share_schema_contract", share.get("schema") == SHARE_SCHEMA)
    check("share_model_contract", share.get("model") == SHARE_MODEL)
    check("share_target_contract", _int(share.get("target_bytes")) == SHARE_TARGET_BYTES)
    check("share_hard_contract", _int(share.get("hard_bytes")) == SHARE_HARD_BYTES)
    check("share_bounds_order", SHARE_TARGET_BYTES < SHARE_HARD_BYTES)
    check("share_single_source", bool(share.get("single_source_of_truth")))

    verdict = doctor.get("verdict") or {}
    verdict_code = str(verdict.get("code") or "")
    check("doctor_verdict_allowed", verdict_code in VERDICT_CODES)
    if _int(severity_counts.get("critical")) == 0 and _int(scores.get("global"), 100) >= 55:
        check("doctor_no_false_critical", verdict_code != "critical", "fail", "Le verdict critique exige un finding critique ou un score <55.")
    if _int((triage.get("lane_counts") or {}).get("fix_now")) > 0 and _int(severity_counts.get("critical")) == 0:
        check("doctor_action_required_semantics", verdict_code == "action_required")

    for item in triage_items:
        ident = str(item.get("id") or "unknown")
        check(f"risk_bounds:{ident}", 0 <= _int(item.get("risk_score"), -1) <= 100)
        check(f"evidence_level:{ident}", str(item.get("evidence_level") or "") in EVIDENCE_LEVELS)
        breakdown = item.get("risk_breakdown") or {}
        components = breakdown.get("components") or {}
        if components:
            check(f"risk_breakdown_math:{ident}", _int(breakdown.get("raw_total")) == sum(_int(v) for v in components.values()))
        check(f"no_auto_fix:{ident}", item.get("repair_safety") != "automatic")

    unproven = [x for x in sem.get("unproven_pairs") or [] if isinstance(x, dict)]
    physical = [x for x in unproven if str(x.get("target_kind") or "") == "actuator"]
    helpers = [x for x in unproven if str(x.get("target_kind") or "") == "helper"]
    check("condition_unproven_identity", _int(sem.get("unproven_pair_count"), len(unproven)) == len(unproven))
    check("condition_physical_identity", _int(sem.get("physical_unproven_pair_count"), len(physical)) == len(physical))
    check("condition_helper_identity", _int(sem.get("helper_unproven_pair_count"), len(helpers)) == len(helpers))
    overlap = sum(1 for x in physical if ((x.get("v7_evidence") or {}).get("numeric_overlap_candidates") or []))
    check("condition_overlap_identity", _int(sem.get("numeric_overlap_candidate_pair_count"), overlap) == overlap)
    for idx, pair in enumerate(physical):
        ev = pair.get("v7_evidence") or {}
        check(f"physical_pair_explainability:{idx}", bool(ev), "warning", "Une paire physique non résolue devrait exposer une preuve V7.")
        check(f"physical_pair_no_template_execution:{idx}", not bool(ev.get("templates_executed", False)))

    external = [x for x in resilience.get("items") or [] if isinstance(x, dict) and x.get("counts_as_external_spof")]
    for status in ("protected", "partial", "review"):
        check(f"resilience_{status}_identity", _int(resilience.get(f"{status}_count")) == sum(1 for x in external if str(x.get("status")) == status))
    true_unprotected = [x for x in external if _int(x.get("unprotected_physical_automation_count")) > 0]
    rec_items = [x for x in recs.get("items") or [] if isinstance(x, dict)]
    if true_unprotected:
        check("resilience_unprotected_recommended", bool(rec_items), "fail")
        if rec_items:
            check("resilience_exposure_first", _int(rec_items[0].get("unprotected_physical_automation_count")) > 0, "fail", "Un contrôle réellement non protégé doit passer avant un fallback seulement faible.")
    check("resilience_must_fix_identity", _int(recs.get("must_fix_count")) == sum(1 for x in rec_items if x.get("tier") == "must_fix"))
    check("resilience_hardening_identity", _int(recs.get("hardening_count")) == sum(1 for x in rec_items if x.get("tier") == "hardening"))

    for key in ("target_resolution_rate", "dynamic_target_resolution_rate", "review_required_ratio", "low_confidence_ratio"):
        if key in flow:
            check(f"flow_bounds:{key}", 0 <= _float(flow.get(key), -1) <= 1)
    check("flow_unresolved_nonnegative", _int(flow.get("unresolved_dynamic_targets")) >= 0)

    for key in ("new_count", "persistent_count", "recurrent_count", "resolved_since_previous_count", "deescalated_since_previous_count"):
        if key in temporal:
            check(f"temporal_nonnegative:{key}", _int(temporal.get(key)) >= 0)
    check("temporal_rapid_rescan_protection", temporal.get("rapid_rescans_promote_persistence") is not True)

    projection = (product.get("score_projection") or {})
    horizons = [projection.get(name) or {} for name in ("after_top_1", "after_top_3", "after_top_5", "after_top_10")]
    scores_h = [_int(x.get("score"), 0) for x in horizons]
    if any(horizons):
        check("projection_monotonic", scores_h == sorted(scores_h))
        check("projection_capped", all(0 <= value <= 100 for value in scores_h))
        gains = [_float(x.get("estimated_gain"), 0) for x in horizons]
        check("projection_gain_monotonic", gains == sorted(gains))

    noise = product.get("entity_noise") or {}
    if noise:
        check("noise_unavailable_nonnegative", _int(noise.get("raw_unavailable")) >= 0)
        check("noise_unknown_nonnegative", _int(noise.get("raw_unknown")) >= 0)
        inv_unavailable = _int(inventory.get("unavailable_count"), _int(noise.get("raw_unavailable")))
        inv_unknown = _int(inventory.get("unknown_count"), _int(noise.get("raw_unknown")))
        check("noise_unavailable_inventory_identity", _int(noise.get("raw_unavailable")) == inv_unavailable)
        check("noise_unknown_inventory_identity", _int(noise.get("raw_unknown")) == inv_unknown)
        check("noise_not_action_count", noise.get("raw_entity_count_used_as_action_count") is False)

    coverage = product.get("diagnostic_coverage") or {}
    if coverage:
        check("coverage_score_bounds", 0 <= _int(coverage.get("score"), -1) <= 100)
        for key in ("quality_gate_pass_ratio", "flow_resolution_ratio", "automation_coverage_ratio"):
            check(f"coverage_ratio:{key}", 0 <= _float(coverage.get(key), -1) <= 1)

    security = product.get("security") or {}
    if security:
        check("security_no_secret_values", security.get("secret_values_in_report") is False)
    limitations = product.get("limitations") or {}
    check("limitations_present", len(limitations.get("items") or []) >= 4)
    check("no_automatic_repairs", _int(product.get("safe_automatic_repairs"), 0) == 0)

    source = str((report.get("diagnostic_summary") or {}).get("source") or "")
    check("no_obsolete_product_source_marker", "v08" not in source.lower(), "warning", "Le résumé final expose encore un marqueur de version produit 0.8.x.")

    bad_privacy_flags = (
        "secrets_yaml_read", "raw_states_persisted", "state_snapshot_persisted",
        "automatic_configuration_changes", "registry_raw_payload_persisted",
        "registry_token_persisted", "flow_raw_yaml_persisted",
        "condition_raw_yaml_persisted", "resilience_raw_yaml_persisted",
        "v090_automatic_configuration_changes", "v100_automatic_configuration_changes",
    )
    for key in bad_privacy_flags:
        if key in privacy:
            check(f"privacy_false:{key}", not bool(privacy.get(key)))
    check("v100_no_extra_state_reads", _int(privacy.get("v100_additional_home_assistant_state_reads"), 0) == 0)

    phases = report.get("scan_performance") or {}
    if phases:
        check("scan_perf_total_nonnegative", _float(phases.get("total_seconds"), -1) >= 0)
        for key, value in (phases.get("phases") or {}).items():
            check(f"scan_perf_phase:{key}", _float(value, -1) >= 0)

    consistency = report.get("consistency_analysis") or {}
    check("legacy_consistency_not_failed", str(consistency.get("status") or "pass") != "fail")

    try:
        encoded = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        check("json_serializable", True)
        check("no_nul", b"\x00" not in encoded)
        check("local_report_size", len(encoded) < 5_000_000, "warning", "Rapport local supérieur à 5 Mo.")
        report_bytes = len(encoded)
    except Exception as exc:
        check("json_serializable", False, "fail", type(exc).__name__)
        report_bytes = None

    status = "fail" if failures else ("warning" if warnings else "pass")
    result = {
        "model": SELF_CHECK_MODEL,
        "version": VERSION,
        "status": status,
        "check_count": check_count,
        "pass_count": max(0, check_count - len(failures) - len(warnings)),
        "warning_count": len(warnings),
        "failure_count": len(failures),
        "failures": failures[:30],
        "warnings": warnings[:30],
        "report_bytes": report_bytes,
        "blocks_publication": bool(failures),
        "read_only": True,
    }
    report["self_check"] = result
    report.setdefault("diagnostic_engine", {})["report_self_check_v2"] = True
    report.setdefault("privacy", {})["self_check_v2_additional_state_reads"] = 0
    return result
