"""HA Doctor 0.14 consolidated scanner pipeline.

Pipeline: one validated acquisition -> V9 semantics -> publication-aware temporal
truth -> product/decision layer -> native self-check -> release gate -> history
publication. No 0.12/0.13 scanner wrapper is invoked and no extra HA state read
is added.
"""

import time
import scanner_v088 as acquisition
import intelligence_v088 as intelligence
from resilience_v100 import build_resilience_recommendations_v3
from semantics_v140 import refine_condition_semantics_v9
from temporal_v140 import apply_temporal_truth_v5, sync_publication_history, validate_current_publication_snapshot
from product_v140 import apply_product_intelligence_v6
from trace_v140 import build_controller_trace_v9
from selfcheck_v140 import run_self_check_v6
from finalize_v140 import finalize_release_v6
from contracts_v140 import VERSION, REPORT_SCHEMA, HISTORY_CONTRACT, HISTORY_POLICY, DECISION_MODEL, CONDITION_MODEL


def _refresh_selfcheck_gate(report):
    sc = report.get("self_check") or {}; quality = report.setdefault("quality_gates", {})
    for gate in quality.get("gates") or []:
        if isinstance(gate, dict) and gate.get("key") == "report_self_check":
            gate.update({
                "status": "fail" if sc.get("failure_count") else ("warning" if sc.get("warning_count") else "pass"),
                "detail": f"{sc.get('pass_count',0)}/{sc.get('check_count',0)} contrôle(s) réussi(s) · {sc.get('warning_count',0)} avertissement(s) · {sc.get('failure_count',0)} échec(s)",
            })
    counts = {}
    for gate in quality.get("gates") or []:
        if isinstance(gate, dict):
            status = str(gate.get("status") or "pass"); counts[status] = counts.get(status, 0) + 1
    quality["counts"] = counts
    quality["overall"] = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")
    quality["non_pass_gates"] = [{k: x.get(k) for k in ("key", "label", "status", "detail")} for x in quality.get("gates") or [] if isinstance(x, dict) and x.get("status") != "pass"]


def _append_publication_validation(report, validation):
    sc = report.setdefault("self_check", {})
    sc["check_count"] = int(sc.get("check_count", 0) or 0) + 1
    if validation.get("valid"):
        sc["pass_count"] = int(sc.get("pass_count", 0) or 0) + 1
        sc["publication_snapshot_self_validated"] = True
        _refresh_selfcheck_gate(report)
        return True
    failures = list(sc.get("failures") or [])
    failures.append({"key": "history.current_publication_snapshot", "detail": str(validation)})
    sc["failures"] = failures[:100]
    sc["failure_count"] = int(sc.get("failure_count", 0) or 0) + 1
    sc["status"] = "fail"; sc["blocks_publication"] = True; sc["publication_snapshot_self_validated"] = False
    trust = report.setdefault("doctor_view", {}).setdefault("trust", {})
    trust["score"] = min(int(trust.get("score", 90) or 90), 50); trust["level"] = "low"; trust["self_check_status"] = "fail"
    _refresh_selfcheck_gate(report)
    return False


def scan(include_yaml=True):
    started = time.monotonic(); phases = {}

    original_semantics = intelligence.refine_condition_semantics_v6
    original_resilience = intelligence.build_resilience_recommendations_v2
    intelligence.refine_condition_semantics_v6 = refine_condition_semantics_v9
    intelligence.build_resilience_recommendations_v2 = build_resilience_recommendations_v3
    try:
        t0 = time.monotonic()
        report = acquisition.scan(include_yaml=include_yaml)
        phases["acquisition_and_core_analysis"] = round(time.monotonic() - t0, 4)
    finally:
        intelligence.refine_condition_semantics_v6 = original_semantics
        intelligence.build_resilience_recommendations_v2 = original_resilience

    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA

    t0 = time.monotonic(); apply_temporal_truth_v5(report); phases["publication_aware_temporal"] = round(time.monotonic() - t0, 4)
    t0 = time.monotonic(); apply_product_intelligence_v6(report); build_controller_trace_v9(report); phases["decision_product_layer"] = round(time.monotonic() - t0, 4)

    report["scan_performance"] = {
        "model": "scan_performance_v5_consolidated_pipeline", "phases": dict(phases),
        "pre_self_check_seconds": round(time.monotonic() - started, 4),
        "total_seconds": round(time.monotonic() - started, 4),
        "single_state_snapshot_preserved": True, "additional_home_assistant_state_reads": 0,
        "consolidated_pipeline": True, "nested_scanner_wrappers": False,
    }
    report.setdefault("privacy", {}).update({
        "v140_additional_home_assistant_state_reads": 0, "v140_automatic_configuration_changes": False,
        "v140_raw_states_persisted": False, "v140_raw_yaml_persisted": False,
        "v140_secret_values_persisted": False, "decision_playbooks_contain_secret_values": False,
    })
    report.setdefault("diagnostic_engine", {}).update({
        "version": "consolidated_decision_engine_0_14", "consolidated_pipeline_v1": True,
        "condition_semantics_v9": True, "controller_review_trace_v2": True,
        "decision_engine_v2": True, "repair_playbooks_v2": True,
        "entity_attention_v3": True, "product_intelligence_v6": True, "self_check_v6_native": True,
        "temporal_v5_publication_aware": True, "history_contract": HISTORY_CONTRACT, "history_policy": HISTORY_POLICY,
        "decision_model": DECISION_MODEL, "condition_model": CONDITION_MODEL,
        "additional_home_assistant_state_reads": 0, "automatic_fix": False, "read_only": True,
    })

    t0 = time.monotonic(); run_self_check_v6(report); phases["native_self_check"] = round(time.monotonic() - t0, 4)
    t0 = time.monotonic(); readiness = finalize_release_v6(report); phases["release_gate"] = round(time.monotonic() - t0, 4)

    publication_allowed = bool(readiness.get("publication_allowed")) and not bool((report.get("self_check") or {}).get("blocks_publication"))
    t0 = time.monotonic()
    sync = sync_publication_history(report, publication_complete=publication_allowed)
    validation = validate_current_publication_snapshot(report, require_published=publication_allowed)
    if not _append_publication_validation(report, validation):
        if publication_allowed:
            sync_publication_history(report, publication_complete=False)
        finalize_release_v6(report)
    phases["history_publication_and_validation"] = round(time.monotonic() - t0, 4)
    report.setdefault("score_history_integrity", {}).update({"current_sync": sync, "current_validation": validation})

    elapsed = round(time.monotonic() - started, 3)
    report["version"] = VERSION; report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report["scan_duration_seconds"] = elapsed
    report["scan_performance"].update({
        "phases": phases, "total_seconds": elapsed,
        "slowest_phase": max(phases, key=phases.get) if phases else None,
        "phase_count": len(phases), "export_validated_during_scan": True,
        "canonical_history_validated_during_scan": True,
        "decision_engine_local_post_processing_only": True,
    })
    return report
