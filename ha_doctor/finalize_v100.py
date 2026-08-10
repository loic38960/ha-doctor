"""Release gate for HA Doctor 0.10 Engine Candidate."""

import finalize_v090 as base
from contracts_v100 import VERSION, READINESS_MODEL, QUALITY_MODEL


def finalize_release_v2(report):
    readiness = base.finalize_release(report)
    if not isinstance(report, dict):
        return readiness

    quality = report.setdefault("quality_gates", {})
    quality["model"] = QUALITY_MODEL
    readiness = report.setdefault("release_readiness", readiness if isinstance(readiness, dict) else {})
    readiness["model"] = READINESS_MODEL
    readiness["engine_candidate"] = True
    readiness["version"] = VERSION
    readiness["automatic_fix"] = False
    readiness["read_only"] = True

    doctor = report.setdefault("doctor_view", {})
    doctor["release_readiness"] = dict(readiness)
    trust = doctor.get("trust") or report.get("diagnostic_trust") or {}
    verdict = doctor.get("verdict") or {}
    doctor["message"] = (
        f"{verdict.get('label','Diagnostic')} · confiance {trust.get('score','—')}/100 · "
        f"moteur 0.10 {str(readiness.get('status','review_required')).replace('_',' ')}."
    )

    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for capability in (
        "report_self_check_v2_cross_contract",
        "release_readiness_v2_engine_candidate",
        "quality_gates_v8_engine_candidate",
    ):
        if capability not in capabilities:
            capabilities.append(capability)
    schema["capabilities"] = capabilities
    report.setdefault("diagnostic_engine", {})["release_readiness_v2"] = True
    return readiness
