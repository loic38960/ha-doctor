"""HA Doctor 0.14 native release gate."""

from contracts_v140 import VERSION, READINESS_MODEL, QUALITY_MODEL, HISTORY_CONTRACT, HISTORY_POLICY


def finalize_release_v6(report):
    self_check = report.get("self_check") or {}
    quality = report.setdefault("quality_gates", {})
    quality["model"] = QUALITY_MODEL
    blocked = bool(self_check.get("blocks_publication")) or self_check.get("status") == "fail"
    warning = self_check.get("status") == "warning" or quality.get("overall") == "warning"
    status = "blocked" if blocked else ("ready_with_warnings" if warning else "ready")
    readiness = {
        "model": READINESS_MODEL, "version": VERSION, "status": status,
        "publication_allowed": not blocked, "native_self_check": True,
        "legacy_report_rewriting": False, "consolidated_pipeline": True,
        "canonical_history_contract": HISTORY_CONTRACT, "canonical_history_policy": HISTORY_POLICY,
        "blocked_reports_can_be_score_baselines": False,
        "export_self_validated": bool(self_check.get("export_self_validated")),
        "decision_engine_self_validated": bool(self_check.get("decision_engine_self_validated")),
        "automatic_fix": False, "read_only": True,
    }
    report["release_readiness"] = readiness
    doctor = report.setdefault("doctor_view", {})
    doctor["release_readiness"] = dict(readiness)
    doctor["message"] = f"{(doctor.get('verdict') or {}).get('label','Diagnostic')} · confiance {(doctor.get('trust') or {}).get('score','—')}/100 · moteur 0.14 {status.replace('_',' ')}."
    report.setdefault("diagnostic_engine", {})["release_readiness_v6_native"] = True
    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for cap in ("report_self_check_v6_native_contracts", "release_readiness_v6_native_gate", "quality_gates_v12_native_contracts", "blocked_snapshot_baseline_prevention"):
        if cap not in capabilities: capabilities.append(cap)
    schema["capabilities"] = capabilities
    return readiness
