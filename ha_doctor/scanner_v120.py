"""HA Doctor 0.12 Temporal Truth Engine scanner.

The validated 0.11 acquisition/semantic pipeline remains the source of Home
Assistant data. 0.12 adds only local post-processing and compact history reads;
it performs zero additional Home Assistant state reads.
"""

import time
import scanner_v110 as base
from contracts_v120 import VERSION, REPORT_SCHEMA, TEMPORAL_MODEL, HISTORY_CONTRACT
from temporal_v120 import apply_temporal_truth_v4, sync_canonical_history
from product_v120 import apply_product_intelligence_v4
from selfcheck_v120 import run_self_check_v4
from finalize_v120 import finalize_release_v4


def scan(include_yaml=True):
    started = time.monotonic()
    phases = {}

    t0 = time.monotonic()
    report = base.scan(include_yaml=include_yaml)
    phases["validated_acquisition_and_core_analysis"] = round(time.monotonic() - t0, 4)
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA

    t0 = time.monotonic()
    apply_temporal_truth_v4(report)
    phases["temporal_truth"] = round(time.monotonic() - t0, 4)

    t0 = time.monotonic()
    apply_product_intelligence_v4(report)
    phases["product_contract_refresh"] = round(time.monotonic() - t0, 4)

    t0 = time.monotonic()
    candidate_sync = sync_canonical_history(report, publication_complete=False)
    phases["canonical_history_candidate"] = round(time.monotonic() - t0, 4)
    report.setdefault("score_history_integrity", {})["current_snapshot_candidate_sync"] = candidate_sync

    elapsed_pre_check = time.monotonic() - started
    report["scan_performance"] = {
        "model": "scan_performance_v3_temporal_truth", "phases": dict(phases),
        "pre_self_check_seconds": round(elapsed_pre_check, 4), "total_seconds": round(elapsed_pre_check, 4),
        "single_state_snapshot_preserved": True, "canonical_history_io_only": True,
    }

    t0 = time.monotonic()
    run_self_check_v4(report)
    phases["self_check_export_and_history_validation"] = round(time.monotonic() - t0, 4)

    t0 = time.monotonic()
    finalize_release_v4(report)
    phases["release_gate"] = round(time.monotonic() - t0, 4)

    publication_complete = not bool((report.get("self_check") or {}).get("blocks_publication"))
    t0 = time.monotonic()
    final_sync = sync_canonical_history(report, publication_complete=publication_complete)
    phases["canonical_history_publish"] = round(time.monotonic() - t0, 4)
    report.setdefault("score_history_integrity", {})["current_snapshot_final_sync"] = final_sync

    elapsed = round(time.monotonic() - started, 3)
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report["scan_duration_seconds"] = elapsed
    report["scan_performance"].update({
        "phases": phases, "total_seconds": elapsed,
        "slowest_phase": max(phases, key=phases.get) if phases else None,
        "phase_count": len(phases), "export_validated_during_scan": True,
        "canonical_history_validated_during_scan": True, "additional_home_assistant_state_reads": 0,
    })
    report.setdefault("temporal_analysis", {}).update({
        "model": TEMPORAL_MODEL, "history_contract": HISTORY_CONTRACT,
        "current_snapshot_publication_complete": publication_complete,
    })
    report.setdefault("privacy", {}).update({
        "v120_additional_home_assistant_state_reads": 0, "v120_automatic_configuration_changes": False,
        "v120_raw_states_persisted": False, "v120_raw_yaml_persisted": False,
        "v120_secret_values_persisted": False, "canonical_history_raw_states_persisted": False,
    })
    report.setdefault("diagnostic_engine", {}).update({
        "version": "temporal_truth_engine_0_12", "condition_semantics_v7": True,
        "resilience_recommendations_v3": True, "product_intelligence_v4": True,
        "self_check_v4": True, "temporal_v4": True, "canonical_history_contract": HISTORY_CONTRACT,
        "support_export_self_validation": True, "public_contract_freshness": True,
    })
    return report
