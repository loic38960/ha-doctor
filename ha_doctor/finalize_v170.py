"""HA Doctor 0.17 resolution/attribution release gate."""

from contracts_v170 import VERSION, QUALITY_MODEL, HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL

READINESS_MODEL = "release_readiness_v9_resolution_attribution"


def finalize_release_v9(report):
    self_check=report.get("self_check") or {}; quality=report.setdefault("quality_gates", {})
    quality["model"] = QUALITY_MODEL
    blocked=bool(self_check.get("blocks_publication")) or self_check.get("status")=="fail"
    warning=self_check.get("status")=="warning" or quality.get("overall")=="warning"
    status="blocked" if blocked else ("ready_with_warnings" if warning else "ready")
    readiness={
        "model":READINESS_MODEL,"version":VERSION,"status":status,"publication_allowed":not blocked,
        "resolution_self_check":True,"score_attribution_validated":True,"replacement_inference_disabled":True,
        "canonical_history_contract":HISTORY_CONTRACT,"canonical_history_policy":HISTORY_POLICY,
        "publication_model":PUBLICATION_MODEL,"blocked_reports_can_be_score_baselines":False,
        "export_self_validated":bool(self_check.get("final_export_self_validated")),
        "automatic_fix":False,"read_only":True,
    }
    report["release_readiness"]=readiness
    doctor=report.setdefault("doctor_view", {}); doctor["release_readiness"]=dict(readiness)
    doctor["message"]=(
        f"{(doctor.get('verdict') or {}).get('label','Diagnostic')} · confiance {(doctor.get('trust') or {}).get('score','—')}/100 · "
        f"moteur 0.17 {status.replace('_',' ')}."
    )
    schema=report.setdefault("report_schema", {}); caps=list(schema.get("capabilities") or [])
    for cap in (
        "diagnostic_resolution_v1","automation_feedback_v2_transition_proof","duplicate_action_semantics_v2_resolution_ready",
        "missing_reference_intelligence_v1","resilience_precision_v6_guard_actionable","temporal_v8_domain_attribution",
        "report_self_check_v9_resolution_truth","assistant_share_report_v11",
    ):
        if cap not in caps: caps.append(cap)
    schema["capabilities"]=caps
    return readiness
