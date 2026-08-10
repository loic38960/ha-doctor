"""HA Doctor 0.10 Engine Candidate scanner.

0.10 keeps the validated single-snapshot 0.8.8 acquisition pipeline and patches
only deterministic semantic/recommendation functions before enrichment. The
new product, self-check and export contracts are pure post-processing and add
zero Home Assistant state reads.
"""

import time

import intelligence_v088 as intelligence
import scanner_v088 as acquisition
from contracts_v100 import VERSION, REPORT_SCHEMA, CONDITION_MODEL
from finalize_v100 import finalize_release_v2
from product_v100 import apply_product_intelligence_v2
from resilience_v100 import build_resilience_recommendations_v3
from selfcheck_v100 import run_self_check_v2
from semantics_v100 import refine_condition_semantics_v7
from temporal_v060 import load_history, save_history


def _sync_history_version(report):
    """Patch only compact metadata on the current temporal snapshot."""
    try:
        path = intelligence.v087.HISTORY_PATH
    except Exception:
        return
    try:
        history = load_history(path)
        generated_at = str(report.get("generated_at") or "")
        if history and str(history[-1].get("generated_at") or "") == generated_at:
            snap = dict(history[-1])
            snap["report_version"] = VERSION
            snap["condition_semantics_model"] = CONDITION_MODEL
            history[-1] = snap
            save_history(history, path)
            report.setdefault("temporal_analysis", {})["final_report_version_synced_v100"] = True
    except Exception:
        report.setdefault("temporal_analysis", {})["final_report_version_synced_v100"] = False


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

    t0 = time.monotonic()
    apply_product_intelligence_v2(report)
    phases["product_intelligence"] = round(time.monotonic() - t0, 4)

    total_before_checks = time.monotonic() - started
    report["scan_performance"] = {
        "model": "scan_performance_v1",
        "phases": dict(phases),
        "pre_self_check_seconds": round(total_before_checks, 4),
        "total_seconds": round(total_before_checks, 4),
        "single_state_snapshot_preserved": True,
    }

    t0 = time.monotonic()
    run_self_check_v2(report)
    phases["self_check"] = round(time.monotonic() - t0, 4)

    t0 = time.monotonic()
    finalize_release_v2(report)
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
    })
    report.setdefault("privacy", {}).update({
        "v100_additional_home_assistant_state_reads": 0,
        "v100_automatic_configuration_changes": False,
        "v100_raw_states_persisted": False,
        "v100_raw_yaml_persisted": False,
        "v100_secret_values_persisted": False,
    })
    report.setdefault("diagnostic_engine", {}).update({
        "version": "engine_candidate_0_10",
        "condition_semantics_v7": True,
        "resilience_recommendations_v3": True,
        "product_intelligence_v2": True,
        "self_check_v2": True,
    })
    return report
