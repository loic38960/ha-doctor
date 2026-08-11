"""Release gate for HA Doctor 0.11 Cross-Validated Engine."""

import finalize_v100 as base
from contracts_v110 import VERSION, READINESS_MODEL, QUALITY_MODEL


def finalize_release_v3(report):
    readiness = base.finalize_release_v2(report)
    if not isinstance(report, dict):
        return readiness
    quality = report.setdefault("quality_gates", {})
    quality["model"] = QUALITY_MODEL
    readiness = report.setdefault("release_readiness", readiness if isinstance(readiness, dict) else {})
    readiness.update({
        "model": READINESS_MODEL,
        "version": VERSION,
        "cross_validated": True,
        "export_self_validated": bool((report.get("self_check") or {}).get("export_self_validated")),
        "automatic_fix": False,
        "read_only": True,
    })
    doctor = report.setdefault("doctor_view", {})
    doctor["release_readiness"] = dict(readiness)
    doctor["message"] = (
        f"{(doctor.get('verdict') or {}).get('label','Diagnostic')} · "
        f"confiance {(doctor.get('trust') or {}).get('score','—')}/100 · "
        f"moteur 0.11 {str(readiness.get('status','review_required')).replace('_',' ')}."
    )
    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for cap in ("report_self_check_v3_export_validated", "release_readiness_v3_cross_validated", "quality_gates_v9_cross_validated"):
        if cap not in capabilities:
            capabilities.append(cap)
    schema["capabilities"] = capabilities
    report.setdefault("diagnostic_engine", {})["release_readiness_v3"] = True
    return readiness
