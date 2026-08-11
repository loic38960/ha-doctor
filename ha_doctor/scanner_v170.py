"""HA Doctor 0.17 Resolution & Attribution scanner.

One Home Assistant acquisition -> exact V11 controller semantics -> actionable
resilience -> Temporal V8 attribution -> Resolution Decision V5 -> staged
publication -> Self-Check V9 -> release gate -> commit/abort -> post-commit
validation. All 0.17 intelligence after acquisition is local read-only processing.
"""

import time
import scanner_v088 as acquisition
import intelligence_v088 as intelligence
from semantics_v160 import refine_condition_semantics_v11
from resilience_v170 import refine_resilience_v6
from temporal_v170 import (
    apply_temporal_truth_v8, stage_publication, commit_publication, abort_publication,
    validate_current_snapshot, refresh_published_baseline_visibility,
)
from product_v170 import apply_product_intelligence_v9, install_public_contract_v170
from selfcheck_v170 import run_self_check_v9, post_commit_validation_v9
from finalize_v170 import finalize_release_v9
from contracts_v170 import (
    VERSION, REPORT_SCHEMA, HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL,
    DECISION_MODEL, CONDITION_MODEL, TEMPORAL_MODEL, SCORE_ATTRIBUTION_MODEL,
)


def _append_publication_failure(report, key, detail):
    sc=report.setdefault("self_check", {}); failures=list(sc.get("failures") or [])
    failures.append({"key":key,"detail":str(detail)}); sc["failures"]=failures[:100]
    sc["failure_count"]=len(sc["failures"]); sc["check_count"]=int(sc.get("check_count",0) or 0)+1
    sc["pass_count"]=max(0,int(sc.get("check_count",0) or 0)-int(sc.get("failure_count",0) or 0)-int(sc.get("warning_count",0) or 0))
    sc["status"]="fail"; sc["blocks_publication"]=True; sc["post_commit_validation"]="fail"
    trust=report.setdefault("doctor_view",{}).setdefault("trust",{})
    trust["score"]=min(int(trust.get("score",90) or 90),50); trust["level"]="low"; trust["self_check_status"]="fail"


def _sync_post_publication_views(report):
    temporal=report.get("temporal_analysis") or {}; product=report.setdefault("product_intelligence", {})
    trace=product.setdefault("score_change_trace", {})
    for key in (
        "current_committed_baseline","canonical_published_including_current","next_scan_baseline_candidate_score",
        "next_scan_baseline_candidate_generated_at","current_domain_scores_persisted",
    ):
        trace[key]=temporal.get(key)
    doctor=report.setdefault("doctor_view",{}); trust=doctor.setdefault("trust",{})
    trust["current_committed_baseline"]=bool(temporal.get("current_committed_baseline"))
    trust["canonical_published_including_current"]=temporal.get("canonical_published_including_current",0)
    trust["domain_score_history_persisted"]=bool(temporal.get("current_domain_scores_persisted"))
    trust["score_attribution_status"]=(report.get("score_attribution") or {}).get("status")
    report["diagnostic_trust"]=trust


def scan(include_yaml=True):
    started=time.monotonic(); phases={}

    original_semantics=intelligence.refine_condition_semantics_v6
    original_resilience=intelligence.build_resilience_recommendations_v2
    intelligence.refine_condition_semantics_v6=refine_condition_semantics_v11
    intelligence.build_resilience_recommendations_v2=refine_resilience_v6
    try:
        t0=time.monotonic(); report=acquisition.scan(include_yaml=include_yaml)
        phases["acquisition_and_core_analysis"]=round(time.monotonic()-t0,4)
    finally:
        intelligence.refine_condition_semantics_v6=original_semantics
        intelligence.build_resilience_recommendations_v2=original_resilience

    report["version"]=VERSION; report.setdefault("report_schema",{})["version"]=REPORT_SCHEMA
    report["scan_performance"]={
        "model":"scan_performance_v8_resolution_attribution","phases":dict(phases),
        "pre_self_check_seconds":round(time.monotonic()-started,4),"total_seconds":round(time.monotonic()-started,4),
        "single_state_snapshot_preserved":True,"additional_home_assistant_state_reads":0,
        "resolution_post_processing_local_only":True,"score_attribution_history_io_only":True,
    }
    report.setdefault("privacy",{}).update({
        "v170_additional_home_assistant_state_reads":0,"v170_automatic_configuration_changes":False,
        "v170_raw_states_persisted":False,"v170_raw_yaml_persisted":False,"v170_secret_values_persisted":False,
        "v170_replacement_entity_ids_inferred":False,
    })

    t0=time.monotonic(); apply_temporal_truth_v8(report); phases["published_baseline_and_attribution"]=round(time.monotonic()-t0,4)
    install_public_contract_v170(report)
    t0=time.monotonic(); apply_product_intelligence_v9(report); phases["resolution_product_and_decision"]=round(time.monotonic()-t0,4)
    install_public_contract_v170(report)

    t0=time.monotonic(); stage=stage_publication(report); phases["publication_stage"]=round(time.monotonic()-t0,4)
    report.setdefault("score_history_integrity",{})["publication_stage"]=stage
    report["scan_performance"]["phases"]=dict(phases); report["scan_performance"]["pre_self_check_seconds"]=round(time.monotonic()-started,4)

    t0=time.monotonic(); run_self_check_v9(report); phases["resolution_self_check_and_export"]=round(time.monotonic()-t0,4)
    t0=time.monotonic(); readiness=finalize_release_v9(report); phases["release_gate"]=round(time.monotonic()-t0,4)

    publication_allowed=bool(readiness.get("publication_allowed")) and not bool((report.get("self_check") or {}).get("blocks_publication"))
    t0=time.monotonic(); sync=None; validation=None
    if publication_allowed:
        sync=commit_publication(report)
        refresh_published_baseline_visibility(report); _sync_post_publication_views(report)
        validation=validate_current_snapshot(report,require_published=True)
        if not validation.get("valid"):
            _append_publication_failure(report,"publication.commit_validation",validation)
            abort_publication(report,reason="commit_validation_failed"); refresh_published_baseline_visibility(report); _sync_post_publication_views(report); finalize_release_v9(report)
        else:
            post=post_commit_validation_v9(report)
            if not post.get("valid"):
                _append_publication_failure(report,"publication.post_commit_validation",post)
                abort_publication(report,reason="post_commit_resolution_validation_failed"); refresh_published_baseline_visibility(report); _sync_post_publication_views(report); finalize_release_v9(report)
            else:
                report.setdefault("self_check",{})["publication_snapshot_self_validated"]=True
    else:
        sync=abort_publication(report,reason="self_check_or_release_gate")
        refresh_published_baseline_visibility(report); _sync_post_publication_views(report)
        validation=validate_current_snapshot(report,require_published=False)
        if not validation.get("valid"):
            _append_publication_failure(report,"publication.abort_validation",validation); finalize_release_v9(report)
    phases["publication_commit_or_abort"]=round(time.monotonic()-t0,4)
    report.setdefault("score_history_integrity",{})["publication_final_sync"]=sync
    report["score_history_integrity"]["publication_final_validation"]=validation

    elapsed=round(time.monotonic()-started,3)
    report["version"]=VERSION; report.setdefault("report_schema",{})["version"]=REPORT_SCHEMA; report["scan_duration_seconds"]=elapsed
    perf=report.setdefault("scan_performance",{})
    perf.update({
        "model":"scan_performance_v8_resolution_attribution","phases":phases,"total_seconds":elapsed,
        "slowest_phase":max(phases,key=phases.get) if phases else None,"phase_count":len(phases),
        "single_state_snapshot_preserved":True,"additional_home_assistant_state_reads":0,
        "resolution_post_processing_local_only":True,"score_attribution_history_io_only":True,
        "final_export_validated_during_scan":True,"publication_transaction_validated_during_scan":True,
        "canonical_order_validated_during_scan":True,
    })
    report.setdefault("diagnostic_engine",{}).update({
        "version":"resolution_attribution_engine_0_17","condition_model":CONDITION_MODEL,
        "decision_model":DECISION_MODEL,"temporal_model":TEMPORAL_MODEL,"score_attribution_model":SCORE_ATTRIBUTION_MODEL,
        "self_check_v9_resolution":True,"history_contract":HISTORY_CONTRACT,"history_policy":HISTORY_POLICY,
        "publication_model":PUBLICATION_MODEL,"additional_home_assistant_state_reads":0,
        "replacement_inference_enabled":False,"automatic_fix":False,"read_only":True,
    })
    return report
