"""HA Doctor 0.13 Decision Engine scanner."""

import time
import scanner_v110 as acquisition_v110
import scanner_v120 as base
from contracts_v130 import VERSION, REPORT_SCHEMA, HISTORY_CONTRACT, DECISION_MODEL, CONDITION_MODEL
from semantics_v130 import refine_condition_semantics_v8
from product_v130 import apply_product_intelligence_v5
from selfcheck_v130 import run_self_check_v5
from finalize_v130 import finalize_release_v5
from temporal_v130 import sync_decision_history, validate_current_decision_snapshot


def _append_history_check(report, validation):
    self_check = report.setdefault("self_check", {})
    self_check["check_count"] = int(self_check.get("check_count", 0) or 0) + 1
    if validation.get("valid"):
        self_check["pass_count"] = int(self_check.get("pass_count", 0) or 0) + 1
        self_check["decision_history_self_validated"] = True
        return
    failures = list(self_check.get("failures") or [])
    failures.append({"key": "v130_decision_history_snapshot", "detail": str(validation)})
    self_check["failures"] = failures[:60]
    self_check["failure_count"] = int(self_check.get("failure_count", 0) or 0) + 1
    self_check["status"] = "fail"
    self_check["blocks_publication"] = True
    self_check["decision_history_self_validated"] = False


def scan(include_yaml=True):
    started = time.monotonic()
    phases = {}

    original_semantics = acquisition_v110.refine_condition_semantics_v7
    acquisition_v110.refine_condition_semantics_v7 = refine_condition_semantics_v8
    try:
        t0 = time.monotonic()
        report = base.scan(include_yaml=include_yaml)
        phases["validated_base_scan_with_v8_semantics"] = round(time.monotonic() - t0, 4)
    finally:
        acquisition_v110.refine_condition_semantics_v7 = original_semantics

    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA

    t0 = time.monotonic()
    apply_product_intelligence_v5(report)
    phases["decision_product_layer"] = round(time.monotonic() - t0, 4)

    t0 = time.monotonic()
    run_self_check_v5(report)
    phases["decision_self_check"] = round(time.monotonic() - t0, 4)

    t0 = time.monotonic()
    candidate = sync_decision_history(report, publication_complete=False)
    validation = validate_current_decision_snapshot(report)
    _append_history_check(report, validation)
    report.setdefault("score_history_integrity", {}).update({
        "v130_candidate_sync": candidate,
        "v130_validation": validation,
        "v130_contract": HISTORY_CONTRACT,
    })
    phases["decision_history_contract"] = round(time.monotonic() - t0, 4)

    publication_complete = not bool((report.get("self_check") or {}).get("blocks_publication"))
    if publication_complete:
        final_sync = sync_decision_history(report, publication_complete=True)
    else:
        final_sync = sync_decision_history(report, publication_complete=False)
    report.setdefault("score_history_integrity", {})["v130_final_sync"] = final_sync

    t0 = time.monotonic()
    finalize_release_v5(report)
    phases["decision_release_gate"] = round(time.monotonic() - t0, 4)

    elapsed = round(time.monotonic() - started, 3)
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report["scan_duration_seconds"] = elapsed
    perf = report.setdefault("scan_performance", {})
    old_phases = dict(perf.get("phases") or {})
    old_phases.update(phases)
    perf.update({
        "model": "scan_performance_v4_decision_engine",
        "phases": old_phases,
        "total_seconds": elapsed,
        "slowest_phase": max(old_phases, key=old_phases.get) if old_phases else None,
        "phase_count": len(old_phases),
        "single_state_snapshot_preserved": True,
        "additional_home_assistant_state_reads": 0,
        "decision_engine_local_post_processing_only": True,
        "canonical_history_validated_during_scan": True,
    })
    report.setdefault("privacy", {}).update({
        "v130_additional_home_assistant_state_reads": 0,
        "v130_automatic_configuration_changes": False,
        "v130_raw_states_persisted": False,
        "v130_raw_yaml_persisted": False,
        "v130_secret_values_persisted": False,
        "decision_playbooks_contain_secret_values": False,
    })
    report.setdefault("diagnostic_engine", {}).update({
        "version": "decision_engine_0_13",
        "condition_semantics_v8": True,
        "decision_engine_v1": True,
        "repair_playbooks_v1": True,
        "entity_attention_v2": True,
        "product_intelligence_v5": True,
        "self_check_v5": True,
        "decision_history_contract": HISTORY_CONTRACT,
        "decision_model": DECISION_MODEL,
        "condition_model": CONDITION_MODEL,
        "automatic_fix": False,
        "read_only": True,
    })
    return report
