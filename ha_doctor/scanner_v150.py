"""HA Doctor 0.15 Trust & Publication scanner.

One acquisition -> acquisition evidence -> V10 semantics -> Temporal V6 ->
current contracts/product/Decision V3 -> staged publication -> Self-Check V7 ->
release gate -> commit/abort -> post-commit validation. No extra HA state read.
"""

import time
import scanner_v088 as acquisition
import intelligence_v088 as intelligence
from resilience_v100 import build_resilience_recommendations_v3
from semantics_v150 import refine_condition_semantics_v10
from temporal_v150 import (
    apply_temporal_truth_v6, stage_publication, commit_publication, abort_publication,
    validate_current_snapshot,
)
from product_v150 import apply_product_intelligence_v7, install_public_contract
from selfcheck_v150 import run_self_check_v7, post_commit_validation
from finalize_v150 import finalize_release_v7
from contracts_v150 import (
    VERSION, REPORT_SCHEMA, HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL,
    DECISION_MODEL, CONDITION_MODEL,
)


def _append_publication_failure(report, key, detail):
    sc = report.setdefault("self_check", {})
    failures = list(sc.get("failures") or [])
    failures.append({"key": key, "detail": str(detail)})
    sc["failures"] = failures[:100]
    sc["failure_count"] = len(sc["failures"])
    sc["check_count"] = int(sc.get("check_count", 0) or 0) + 1
    sc["pass_count"] = max(0, int(sc.get("check_count", 0) or 0) - int(sc.get("failure_count", 0) or 0) - int(sc.get("warning_count", 0) or 0))
    sc["status"] = "fail"; sc["blocks_publication"] = True
    sc["post_commit_validation"] = "fail"
    trust = report.setdefault("doctor_view", {}).setdefault("trust", {})
    trust["score"] = min(int(trust.get("score", 90) or 90), 50); trust["level"] = "low"; trust["self_check_status"] = "fail"


def scan(include_yaml=True):
    started = time.monotonic(); phases = {}

    original_semantics = intelligence.refine_condition_semantics_v6
    original_resilience = intelligence.build_resilience_recommendations_v2
    intelligence.refine_condition_semantics_v6 = refine_condition_semantics_v10
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

    # Acquisition evidence must exist BEFORE product/trust computation.
    report["scan_performance"] = {
        "model": "scan_performance_v6_trust_first", "phases": dict(phases),
        "pre_self_check_seconds": round(time.monotonic() - started, 4),
        "total_seconds": round(time.monotonic() - started, 4),
        "single_state_snapshot_preserved": True, "additional_home_assistant_state_reads": 0,
        "consolidated_pipeline": True, "nested_scanner_wrappers": False,
        "trust_evidence_installed_before_product": True,
    }
    report.setdefault("privacy", {}).update({
        "v150_additional_home_assistant_state_reads": 0, "v150_automatic_configuration_changes": False,
        "v150_raw_states_persisted": False, "v150_raw_yaml_persisted": False,
        "v150_secret_values_persisted": False, "decision_playbooks_contain_secret_values": False,
    })

    t0 = time.monotonic(); apply_temporal_truth_v6(report); phases["publication_aware_temporal"] = round(time.monotonic() - t0, 4)
    install_public_contract(report)
    t0 = time.monotonic(); apply_product_intelligence_v7(report); phases["trust_first_product_and_decision"] = round(time.monotonic() - t0, 4)

    # Stage current snapshot with no canonical score contract before validation.
    t0 = time.monotonic(); stage = stage_publication(report); phases["publication_stage"] = round(time.monotonic() - t0, 4)
    report.setdefault("score_history_integrity", {})["publication_stage"] = stage

    report["scan_performance"]["phases"] = dict(phases)
    report["scan_performance"]["pre_self_check_seconds"] = round(time.monotonic() - started, 4)

    t0 = time.monotonic(); run_self_check_v7(report); phases["final_export_self_check"] = round(time.monotonic() - t0, 4)
    t0 = time.monotonic(); readiness = finalize_release_v7(report); phases["release_gate"] = round(time.monotonic() - t0, 4)

    publication_allowed = bool(readiness.get("publication_allowed")) and not bool((report.get("self_check") or {}).get("blocks_publication"))
    t0 = time.monotonic()
    if publication_allowed:
        sync = commit_publication(report)
        validation = validate_current_snapshot(report, require_published=True)
        if not validation.get("valid"):
            _append_publication_failure(report, "publication.commit_validation", validation)
            abort_publication(report, reason="commit_validation_failed")
            finalize_release_v7(report)
        else:
            post = post_commit_validation(report)
            if not post.get("valid"):
                abort_publication(report, reason="post_commit_validation_failed")
                finalize_release_v7(report)
            else:
                report.setdefault("self_check", {})["publication_snapshot_self_validated"] = True
    else:
        sync = abort_publication(report, reason="self_check_or_release_gate")
        validation = validate_current_snapshot(report, require_published=False)
        if not validation.get("valid"):
            _append_publication_failure(report, "publication.abort_validation", validation)
            finalize_release_v7(report)
    phases["publication_commit_or_abort"] = round(time.monotonic() - t0, 4)
    report.setdefault("score_history_integrity", {})["publication_final_sync"] = sync
    report["score_history_integrity"]["publication_final_validation"] = validation

    elapsed = round(time.monotonic() - started, 3)
    report["version"] = VERSION; report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report["scan_duration_seconds"] = elapsed
    perf = report.setdefault("scan_performance", {})
    perf.update({
        "model": "scan_performance_v6_trust_first", "phases": phases, "total_seconds": elapsed,
        "slowest_phase": max(phases, key=phases.get) if phases else None, "phase_count": len(phases),
        "single_state_snapshot_preserved": True, "additional_home_assistant_state_reads": 0,
        "trust_evidence_installed_before_product": True, "final_export_validated_during_scan": True,
        "publication_transaction_validated_during_scan": True, "decision_engine_local_post_processing_only": True,
    })
    report.setdefault("diagnostic_engine", {}).update({
        "version": "trust_publication_engine_0_15", "consolidated_pipeline_v2": True,
        "condition_semantics_v10": True, "decision_engine_v3": True, "repair_playbooks_v3": True,
        "entity_attention_v4": True, "product_intelligence_v7": True, "self_check_v7_final_export": True,
        "temporal_v6_publication_transaction": True, "history_contract": HISTORY_CONTRACT,
        "history_policy": HISTORY_POLICY, "publication_model": PUBLICATION_MODEL,
        "decision_model": DECISION_MODEL, "condition_model": CONDITION_MODEL,
        "additional_home_assistant_state_reads": 0, "automatic_fix": False, "read_only": True,
    })
    return report
