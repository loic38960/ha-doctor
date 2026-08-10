"""Final publication gate for HA Doctor 0.9 reports."""
from collections import Counter

VERSION = "0.9.0"
MODEL = "release_readiness_v1"


def finalize_release(report):
    if not isinstance(report, dict):
        return report
    self_check = report.get("self_check") or {}
    self_status = str(self_check.get("status") or "warning")
    trust = report.setdefault("diagnostic_trust", {})
    doctor = report.setdefault("doctor_view", {})

    try:
        trust_score = int(trust.get("score", 0) or 0)
    except Exception:
        trust_score = 0

    reasons = list(trust.get("deduction_reasons") or [])
    if self_status == "fail":
        trust_score = min(trust_score, 50)
        if "report_self_check_failure" not in reasons:
            reasons.append("report_self_check_failure")
    elif self_status == "warning":
        trust_score = max(0, trust_score - 5)
        if "report_self_check_warning" not in reasons:
            reasons.append("report_self_check_warning")
    trust["score"] = trust_score
    trust["level"] = "high" if trust_score >= 85 else ("medium" if trust_score >= 65 else "low")
    trust["self_check_status"] = self_status
    trust["deduction_reasons"] = reasons
    doctor["trust"] = dict(trust)

    quality = report.setdefault("quality_gates", {})
    gates = [dict(item) for item in quality.get("gates") or [] if isinstance(item, dict)]
    gates = [item for item in gates if str(item.get("key") or "") != "report_self_check"]
    gates.append({
        "key": "report_self_check",
        "label": "Auto-contrôle du rapport",
        "status": self_status,
        "detail": (
            f"{self_check.get('pass_count',0)}/{self_check.get('check_count',0)} contrôle(s) réussi(s) · "
            f"{self_check.get('warning_count',0)} avertissement(s) · {self_check.get('failure_count',0)} échec(s)"
        ),
    })
    counts = Counter(str(item.get("status") or "warning") for item in gates)
    quality["gates"] = gates
    quality["counts"] = dict(counts)
    quality["model"] = "quality_gates_v7_self_checked"
    quality["overall"] = "fail" if counts.get("fail") else ("warning" if counts.get("warning") else "pass")

    if self_status == "fail" or quality["overall"] == "fail":
        status = "blocked"
    elif trust_score < 65:
        status = "review_required"
    elif quality["overall"] == "warning" or self_status == "warning":
        status = "ready_with_warnings"
    else:
        status = "ready"

    readiness = {
        "model": MODEL,
        "status": status,
        "publishable": status in {"ready", "ready_with_warnings"},
        "self_check_status": self_status,
        "quality_status": quality["overall"],
        "diagnostic_trust_score": trust_score,
        "diagnostic_trust_level": trust.get("level"),
        "primary_score_unchanged": True,
        "automatic_fix": False,
        "read_only": True,
    }
    report["release_readiness"] = readiness
    doctor["release_readiness"] = readiness
    verdict = doctor.get("verdict") or {}
    doctor["message"] = (
        f"{verdict.get('label','Diagnostic')} · confiance {trust_score}/100 · "
        f"publication {status.replace('_',' ')}."
    )

    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for capability in ("report_self_check_quality_gate", "release_readiness_v1", "trust_self_check_feedback"):
        if capability not in capabilities:
            capabilities.append(capability)
    schema["capabilities"] = capabilities
    report.setdefault("diagnostic_engine", {})["release_readiness_v1"] = True
    report.setdefault("privacy", {})["release_readiness_additional_state_reads"] = 0
    return readiness
