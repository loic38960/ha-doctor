"""Release gate for HA Doctor 0.12 Temporal Truth Engine."""

import finalize_v110 as base
from contracts_v120 import VERSION, READINESS_MODEL, QUALITY_MODEL, HISTORY_CONTRACT


def finalize_release_v4(report):
    readiness = base.finalize_release_v3(report)
    if not isinstance(report, dict):
        return readiness
    report.setdefault("quality_gates", {})["model"] = QUALITY_MODEL
    readiness = report.setdefault("release_readiness", readiness if isinstance(readiness, dict) else {})
    readiness.update({
        "model": READINESS_MODEL, "version": VERSION, "temporal_truth": True,
        "canonical_history_contract": HISTORY_CONTRACT, "legacy_score_guessing": False,
        "public_contracts_validated": bool((report.get("self_check") or {}).get("public_contracts_self_validated")),
        "temporal_history_validated": bool((report.get("self_check") or {}).get("temporal_history_self_validated")),
        "export_self_validated": bool((report.get("self_check") or {}).get("export_self_validated")),
        "automatic_fix": False, "read_only": True,
    })
    doctor = report.setdefault("doctor_view", {})
    doctor["release_readiness"] = dict(readiness)
    doctor["message"] = f"{(doctor.get('verdict') or {}).get('label','Diagnostic')} · confiance {(doctor.get('trust') or {}).get('score','—')}/100 · moteur 0.12 {str(readiness.get('status','review_required')).replace('_',' ')}."
    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for cap in ("report_self_check_v4_temporal_contracts", "release_readiness_v4_temporal_truth", "quality_gates_v10_temporal_truth", "canonical_published_score_history", "public_contract_freshness_gate"):
        if cap not in capabilities:
            capabilities.append(cap)
    schema["capabilities"] = capabilities
    report.setdefault("diagnostic_engine", {})["release_readiness_v4"] = True
    return readiness
