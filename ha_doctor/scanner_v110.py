"""HA Doctor 0.11 Cross-Validated Engine scanner."""

import time

import intelligence_v088 as intelligence
import scanner_v088 as acquisition
from contracts_v110 import VERSION, REPORT_SCHEMA, CONDITION_MODEL
from finalize_v110 import finalize_release_v3
from product_v110 import apply_product_intelligence_v3
from resilience_v100 import build_resilience_recommendations_v3
from selfcheck_v110 import run_self_check_v3
from semantics_v100 import refine_condition_semantics_v7
from temporal_v060 import load_history, save_history


def _sync_history_version(report):
    try:
        path = intelligence.v087.HISTORY_PATH
        history = load_history(path)
        generated_at = str(report.get("generated_at") or "")
        if history and str(history[-1].get("generated_at") or "") == generated_at:
            snap = dict(history[-1])
            snap["report_version"] = VERSION
            snap["condition_semantics_model"] = CONDITION_MODEL
            history[-1] = snap
            save_history(history, path)
            report.setdefault("temporal_analysis", {})["final_report_version_synced_v110"] = True
    except Exception:
        report.setdefault("temporal_analysis", {})["final_report_version_synced_v110"] = False


def scan(include_yaml=True):
    started = time.monotonic()
    phases = {}
    original_semantics = intelligence.refine_condition_semantics_v6
    original_resilience = intelligence.build_resilience_recommendations_v2
    intelligence.refine_condition_semantics_v6 = refine_condition_semantics_v7
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

    elapsed_pre_product = time.monotonic() - started
    report["scan_performance"] = {
        "model": "scan_performance_v2_cross_validated",
        "phases": dict(phases),
        "pre_self_check_seconds": round(elapsed_pre_product, 4),
        "total_seconds": round(elapsed_pre_product, 4),
        "single_state_snapshot_preserved": True,
    }

    t0 = time.monotonic()
    apply_product_intelligence_v3(report)
    phases["product_intelligence"] = round(time.monotonic() - t0, 4)

    t0 = time.monotonic()
    run_self_check_v3(report)
    phases["self_check_and_export_validation"] = round(time.monotonic() - t0, 4)

    t0 = time.monotonic()
    finalize_release_v3(report)
    phases["release_gate"] = round(time.monotonic() - t0, 4)

    _sync_history_version(report)
    elapsed = round(time.monotonic() - started, 3)
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report["scan_duration_seconds"] = elapsed
    report["scan_performance"].update({
        "phases": phases,
        "total_seconds": elapsed,
        "slowest_phase": max(phases, key=phases.get) if phases else None,
        "phase_count": len(phases),
        "export_validated_during_scan": True,
    })
    report.setdefault("privacy", {}).update({
        "v110_additional_home_assistant_state_reads": 0,
        "v110_automatic_configuration_changes": False,
        "v110_raw_states_persisted": False,
        "v110_raw_yaml_persisted": False,
        "v110_secret_values_persisted": False,
    })
    report.setdefault("diagnostic_engine", {}).update({
        "version": "cross_validated_engine_0_11",
        "condition_semantics_v7": True,
        "resilience_recommendations_v3": True,
        "product_intelligence_v3": True,
        "self_check_v3": True,
        "support_export_self_validation": True,
    })
    return report
