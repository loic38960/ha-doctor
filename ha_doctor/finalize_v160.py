"""HA Doctor 0.16 precision release gate."""

from contracts_v160 import VERSION, READINESS_MODEL, QUALITY_MODEL, HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL


def finalize_release_v8(report):
    self_check = report.get("self_check") or {}; quality = report.setdefault("quality_gates", {})
    quality["model"] = QUALITY_MODEL
    blocked = bool(self_check.get("blocks_publication")) or self_check.get("status") == "fail"
    warning = self_check.get("status") == "warning" or quality.get("overall") == "warning"
    status = "blocked" if blocked else ("ready_with_warnings" if warning else "ready")
    readiness = {
        "model": READINESS_MODEL, "version": VERSION, "status": status,
        "publication_allowed": not blocked, "precision_self_check": True,
        "canonical_order_required": True, "exact_controller_scope_required": True,
        "phase_aware_resilience_required": True, "canonical_history_contract": HISTORY_CONTRACT,
        "canonical_history_policy": HISTORY_POLICY, "publication_model": PUBLICATION_MODEL,
        "blocked_reports_can_be_score_baselines": False,
        "export_self_validated": bool(self_check.get("final_export_self_validated")),
        "automatic_fix": False, "read_only": True,
    }
    report["release_readiness"] = readiness
    doctor = report.setdefault("doctor_view", {}); doctor["release_readiness"] = dict(readiness)
    doctor["message"] = f"{(doctor.get('verdict') or {}).get('label','Diagnostic')} · confiance {(doctor.get('trust') or {}).get('score','—')}/100 · moteur 0.16 {status.replace('_',' ')}."
    schema = report.setdefault("report_schema", {}); caps = list(schema.get("capabilities") or [])
    for cap in ("report_self_check_v8_precision_truth", "release_readiness_v8_precision_gate", "quality_gates_v14_precision_validated", "canonical_order_release_guard"):
        if cap not in caps: caps.append(cap)
    schema["capabilities"] = caps
    return readiness
