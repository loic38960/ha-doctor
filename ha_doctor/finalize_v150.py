"""HA Doctor 0.15 publication-transaction release gate."""

from contracts_v150 import (
    VERSION, READINESS_MODEL, QUALITY_MODEL, HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL,
)


def finalize_release_v7(report):
    sc = report.get("self_check") or {}
    quality = report.setdefault("quality_gates", {})
    quality["model"] = QUALITY_MODEL
    truth = (report.get("product_intelligence") or {}).get("public_contract_truth") or {}
    truth_ok = all(bool(v) for k, v in truth.items() if k.endswith("_fresh")) and bool(truth.get("decision_item_identity"))
    snapshot_ok = bool((report.get("scan_performance") or {}).get("single_state_snapshot_preserved"))
    export_ok = bool(sc.get("final_export_self_validated"))
    blocked = bool(sc.get("blocks_publication")) or sc.get("status") == "fail" or not truth_ok or not snapshot_ok or not export_ok
    warning = sc.get("status") == "warning" or quality.get("overall") == "warning"
    status = "blocked" if blocked else ("ready_with_warnings" if warning else "ready")
    readiness = {
        "model": READINESS_MODEL, "version": VERSION, "status": status,
        "publication_allowed": not blocked, "publication_model": PUBLICATION_MODEL,
        "native_self_check": True, "final_export_self_validated": export_ok,
        "public_contract_truth_validated": truth_ok, "single_snapshot_validated": snapshot_ok,
        "legacy_report_rewriting": False, "consolidated_pipeline": True,
        "canonical_history_contract": HISTORY_CONTRACT, "canonical_history_policy": HISTORY_POLICY,
        "blocked_reports_can_be_score_baselines": False, "automatic_fix": False, "read_only": True,
    }
    report["release_readiness"] = readiness
    doctor = report.setdefault("doctor_view", {})
    doctor["release_readiness"] = dict(readiness)
    doctor["message"] = f"{(doctor.get('verdict') or {}).get('label','Diagnostic')} · confiance {(doctor.get('trust') or {}).get('score','—')}/100 · moteur 0.15 {status.replace('_',' ')}."
    report.setdefault("diagnostic_engine", {})["release_readiness_v7_publication_transaction"] = True
    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for cap in ("report_self_check_v7_final_export_truth", "release_readiness_v7_publication_transaction", "quality_gates_v13_publication_safe", "post_commit_publication_revoke"):
        if cap not in capabilities:
            capabilities.append(cap)
    schema["capabilities"] = capabilities
    return readiness
