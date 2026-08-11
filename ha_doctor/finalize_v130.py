"""Release gate for HA Doctor 0.13 Decision Engine."""

import finalize_v120 as base
from contracts_v130 import VERSION, READINESS_MODEL, QUALITY_MODEL, DECISION_MODEL, CONDITION_MODEL, HISTORY_CONTRACT


def finalize_release_v5(report):
    readiness = base.finalize_release_v4(report)
    if not isinstance(report, dict):
        return readiness
    report.setdefault("quality_gates", {})["model"] = QUALITY_MODEL
    decision = report.get("decision_engine") or {}
    sem = report.get("condition_semantics") or {}
    self_check = report.get("self_check") or {}
    readiness = report.setdefault("release_readiness", readiness if isinstance(readiness, dict) else {})
    readiness.update({
        "model": READINESS_MODEL,
        "version": VERSION,
        "decision_engine": decision.get("model") == DECISION_MODEL,
        "decision_items": decision.get("total", 0),
        "repair_playbooks_complete": bool(self_check.get("decision_engine_self_validated")),
        "mandatory_guard_semantics": sem.get("model") == CONDITION_MODEL,
        "mandatory_guard_proofs_validated": bool(self_check.get("mandatory_guard_proofs_self_validated")),
        "canonical_history_contract": HISTORY_CONTRACT,
        "export_self_validated": bool(self_check.get("export_self_validated")),
        "automatic_fix": False,
        "read_only": True,
    })
    doctor = report.setdefault("doctor_view", {})
    doctor["release_readiness"] = dict(readiness)
    doctor["message"] = (
        f"{(doctor.get('verdict') or {}).get('label','Diagnostic')} · "
        f"confiance {(doctor.get('trust') or {}).get('score','—')}/100 · "
        f"moteur 0.13 {str(readiness.get('status','review_required')).replace('_',' ')} · "
        f"{decision.get('ready_for_manual_change_count',0)} action(s) prête(s)."
    )
    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for cap in (
        "report_self_check_v5_decision_contracts", "release_readiness_v5_decision_engine",
        "quality_gates_v11_decision_engine", "decision_playbook_release_gate",
        "mandatory_guard_proof_release_gate",
    ):
        if cap not in capabilities:
            capabilities.append(cap)
    schema["capabilities"] = capabilities
    report.setdefault("diagnostic_engine", {})["release_readiness_v5"] = True
    return readiness
