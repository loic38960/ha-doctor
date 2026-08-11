"""HA Doctor 0.16 Evidence Precision scanner.

One Home Assistant acquisition -> V11 exact controller scope + phase-aware
resilience -> Temporal V7 -> precision product/automation evidence -> staged
publication -> Self-Check V8 -> release gate -> commit/abort -> post-commit
baseline visibility. No additional Home Assistant state read.
"""

import time
import scanner_v088 as acquisition
import intelligence_v088 as intelligence
from semantics_v160 import refine_condition_semantics_v11
from resilience_v160 import refine_resilience_v5
from temporal_v160 import (
    apply_temporal_truth_v7, stage_publication, commit_publication, abort_publication,
    validate_current_snapshot, refresh_published_baseline_visibility,
)
from product_v160 import apply_product_intelligence_v8, install_public_contract_v160
from selfcheck_v160 import run_self_check_v8, post_commit_validation_v8
from finalize_v160 import finalize_release_v8
from hotfix_v161 import apply_hotfix_v161
from contracts_v160 import (
    VERSION, REPORT_SCHEMA, HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL,
    DECISION_MODEL, CONDITION_MODEL, CONTROLLER_IMPACT_MODEL, RESILIENCE_MODEL,
)


def _append_publication_failure(report, key, detail):
    sc = report.setdefault("self_check", {}); failures = list(sc.get("failures") or [])
    failures.append({"key": key, "detail": str(detail)}); sc["failures"] = failures[:100]
    sc["failure_count"] = len(sc["failures"]); sc["check_count"] = int(sc.get("check_count", 0) or 0) + 1
    sc["pass_count"] = max(0, int(sc.get("check_count", 0) or 0) - int(sc.get("failure_count", 0) or 0) - int(sc.get("warning_count", 0) or 0))
    sc["status"] = "fail"; sc["blocks_publication"] = True; sc["post_commit_validation"] = "fail"
    trust = report.setdefault("doctor_view", {}).setdefault("trust", {})
    trust["score"] = min(int(trust.get("score", 90) or 90), 50); trust["level"] = "low"; trust["self_check_status"] = "fail"


def _sync_post_publication_views(report):
    temporal = report.get("temporal_analysis") or {}; product = report.setdefault("product_intelligence", {})
    trace = product.setdefault("score_change_trace", {})
    trace["current_committed_baseline"] = bool(temporal.get("current_committed_baseline"))
    trace["canonical_published_including_current"] = temporal.get("canonical_published_including_current", 0)
    trace["next_scan_baseline_candidate_score"] = temporal.get("next_scan_baseline_candidate_score")
    doctor = report.setdefault("doctor_view", {}); trust = doctor.setdefault("trust", {})
    trust["current_committed_baseline"] = bool(temporal.get("current_committed_baseline"))
    trust["canonical_published_including_current"] = temporal.get("canonical_published_including_current", 0)
    report["diagnostic_trust"] = trust


def scan(include_yaml=True):
    started = time.monotonic(); phases = {}

    original_semantics = intelligence.refine_condition_semantics_v6
    original_resilience = intelligence.build_resilience_recommendations_v2
    intelligence.refine_condition_semantics_v6 = refine_condition_semantics_v11
    intelligence.build_resilience_recommendations_v2 = refine_resilience_v5
    try:
        t0 = time.monotonic(); report = acquisition.scan(include_yaml=include_yaml)
        phases["acquisition_and_core_analysis"] = round(time.monotonic() - t0, 4)
    finally:
        intelligence.refine_condition_semantics_v6 = original_semantics
        intelligence.build_resilience_recommendations_v2 = original_resilience

    report["version"] = VERSION; report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report["scan_performance"] = {
        "model": "scan_performance_v7_evidence_precision", "phases": dict(phases),
        "pre_self_check_seconds": round(time.monotonic() - started, 4), "total_seconds": round(time.monotonic() - started, 4),
        "single_state_snapshot_preserved": True, "additional_home_assistant_state_reads": 0,
        "precision_post_processing_local_only": True, "trust_evidence_installed_before_product": True,
    }
    report.setdefault("privacy", {}).update({
        "v160_additional_home_assistant_state_reads": 0, "v160_automatic_configuration_changes": False,
        "v160_raw_states_persisted": False, "v160_raw_yaml_persisted": False,
        "v160_secret_values_persisted": False, "precision_playbooks_contain_secret_values": False,
    })

    t0 = time.monotonic(); apply_temporal_truth_v7(report); phases["published_baseline_temporal"] = round(time.monotonic() - t0, 4)
    install_public_contract_v160(report)
    t0 = time.monotonic(); apply_product_intelligence_v8(report); phases["precision_product_and_decision"] = round(time.monotonic() - t0, 4)
    install_public_contract_v160(report)
    t0 = time.monotonic(); apply_hotfix_v161(report); phases["publication_contract_hotfix"] = round(time.monotonic() - t0, 4)

    t0 = time.monotonic(); stage = stage_publication(report); phases["publication_stage"] = round(time.monotonic() - t0, 4)
    report.setdefault("score_history_integrity", {})["publication_stage"] = stage
    report["scan_performance"]["phases"] = dict(phases); report["scan_performance"]["pre_self_check_seconds"] = round(time.monotonic() - started, 4)

    t0 = time.monotonic(); run_self_check_v8(report); phases["precision_self_check"] = round(time.monotonic() - t0, 4)
    t0 = time.monotonic(); readiness = finalize_release_v8(report); phases["release_gate"] = round(time.monotonic() - t0, 4)

    publication_allowed = bool(readiness.get("publication_allowed")) and not bool((report.get("self_check") or {}).get("blocks_publication"))
    t0 = time.monotonic(); sync = None; validation = None
    if publication_allowed:
        sync = commit_publication(report)
        refresh_published_baseline_visibility(report); _sync_post_publication_views(report)
        validation = validate_current_snapshot(report, require_published=True)
        if not validation.get("valid"):
            _append_publication_failure(report, "publication.commit_validation", validation)
            abort_publication(report, reason="commit_validation_failed"); refresh_published_baseline_visibility(report); _sync_post_publication_views(report)
            finalize_release_v8(report)
        else:
            post = post_commit_validation_v8(report)
            if not post.get("valid"):
                abort_publication(report, reason="post_commit_precision_validation_failed"); refresh_published_baseline_visibility(report); _sync_post_publication_views(report)
                finalize_release_v8(report)
            else:
                report.setdefault("self_check", {})["publication_snapshot_self_validated"] = True
    else:
        sync = abort_publication(report, reason="self_check_or_release_gate")
        refresh_published_baseline_visibility(report); _sync_post_publication_views(report)
        validation = validate_current_snapshot(report, require_published=False)
        if not validation.get("valid"):
            _append_publication_failure(report, "publication.abort_validation", validation); finalize_release_v8(report)
    phases["publication_commit_or_abort"] = round(time.monotonic() - t0, 4)
    report.setdefault("score_history_integrity", {})["publication_final_sync"] = sync
    report["score_history_integrity"]["publication_final_validation"] = validation

    elapsed = round(time.monotonic() - started, 3)
    report["version"] = VERSION; report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA; report["scan_duration_seconds"] = elapsed
    perf = report.setdefault("scan_performance", {})
    perf.update({
        "model": "scan_performance_v7_evidence_precision", "phases": phases, "total_seconds": elapsed,
        "slowest_phase": max(phases, key=phases.get) if phases else None, "phase_count": len(phases),
        "single_state_snapshot_preserved": True, "additional_home_assistant_state_reads": 0,
        "precision_post_processing_local_only": True, "final_export_validated_during_scan": True,
        "publication_transaction_validated_during_scan": True, "canonical_order_validated_during_scan": True,
    })
    report.setdefault("diagnostic_engine", {}).update({
        "version": "evidence_precision_engine_0_16_1", "condition_semantics_v11": True,
        "controller_impact_model": CONTROLLER_IMPACT_MODEL, "resilience_precision_model": RESILIENCE_MODEL,
        "decision_engine_v4": True, "automation_precision_v1": True, "self_check_v8_precision": True,
        "temporal_v7_baseline_visibility": True, "history_contract": HISTORY_CONTRACT,
        "history_policy": HISTORY_POLICY, "publication_model": PUBLICATION_MODEL,
        "decision_model": DECISION_MODEL, "condition_model": CONDITION_MODEL,
        "v161_publication_hotfix": True,
        "additional_home_assistant_state_reads": 0, "automatic_fix": False, "read_only": True,
    })
    return report
