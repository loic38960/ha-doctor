"""HA Doctor 0.11 self-check: validate both full report and support export."""

from contracts_v110 import VERSION, SELF_CHECK_MODEL, SHARE_HARD_BYTES, SHARE_TARGET_BYTES
import selfcheck_v100 as base
from product_v110 import finding_evidence_count
from sharing_v110 import build_share_report


def _int(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return int(default)


def _finding(report, rule_id):
    return next((x for x in report.get("findings") or [] if isinstance(x, dict) and x.get("rule_id") == rule_id), {})


def run_self_check_v3(report):
    # Reuse all 0.10 invariants without letting its hard-coded public contract
    # reject the newer additive 0.11 envelope.
    saved_version = report.get("version")
    saved_schema = dict(report.get("report_schema") or {})
    saved_share = dict(report.get("share_contract") or {})
    report["version"] = "0.10.0"
    report.setdefault("report_schema", {})["version"] = "ha-doctor-report/0.10"
    report["share_contract"] = {
        "schema": "ha-doctor-share/4",
        "model": "assistant_share_report_v4",
        "target_bytes": 28000,
        "hard_bytes": 32000,
        "single_source_of_truth": True,
    }
    base_result = base.run_self_check_v2(report)
    report["version"] = saved_version
    report["report_schema"] = saved_schema
    report["share_contract"] = saved_share

    failures = list(base_result.get("failures") or [])
    warnings = list(base_result.get("warnings") or [])
    check_count = _int(base_result.get("check_count"), 0)

    def check(key, ok, severity="fail", detail=None):
        nonlocal check_count
        check_count += 1
        if ok:
            return
        (failures if severity == "fail" else warnings).append({"key": key, "detail": detail or key})

    product = report.get("product_intelligence") or {}
    security = product.get("security") or {}
    maintenance = product.get("maintenance") or {}
    truth = product.get("cross_section_truth") or {}
    perf = report.get("scan_performance") or {}
    doctor = report.get("doctor_view") or {}
    trust = doctor.get("trust") or report.get("diagnostic_trust") or {}

    active = finding_evidence_count(_finding(report, "HD-SEC-001"))
    archive = finding_evidence_count(_finding(report, "HD-SEC-003"))
    missing = finding_evidence_count(_finding(report, "HD-CFG-001"))
    local = finding_evidence_count(_finding(report, "HD-REG-002"))
    check("security_active_source_identity", _int(security.get("active_secret_hint_count")) == active)
    check("security_archive_source_identity", _int(security.get("archive_secret_hint_count")) == archive)
    check("security_posture_source_identity", security.get("posture") == ("action_required" if active else ("review" if archive else "good")))
    check("maintenance_missing_ref_source_identity", _int(maintenance.get("missing_reference_count")) == missing)
    check("maintenance_local_review_source_identity", _int(maintenance.get("local_unavailable_review")) == local)
    check("cross_section_truth_complete", all(
        bool(value) for key, value in truth.items() if key.endswith("_matches_finding")
    ))

    if perf.get("single_state_snapshot_preserved"):
        check("trust_single_snapshot_identity", trust.get("single_snapshot_evidence") is True)

    controller = product.get("controller_review_trace") or {}
    for idx, item in enumerate(controller.get("items") or []):
        check(f"controller_trace_present:{idx}", bool(item.get("reason")))
        check(f"controller_templates_not_executed:{idx}", item.get("templates_executed") is False)

    resilience = product.get("resilience_trace") or {}
    for idx, item in enumerate(resilience.get("items") or []):
        exposed = _int(item.get("unprotected_physical_automation_count")) + _int(item.get("weak_physical_automation_count"))
        if exposed:
            check(f"resilience_risky_automation_trace:{idx}", bool(item.get("risky_automations")), "fail", "Une recommandation de résilience doit nommer au moins une automatisation concernée.")

    executive = str((report.get("executive_summary") or {}).get("text") or "")
    check("executive_mentions_v7", "Contrôleurs V7" in executive)
    check("executive_mentions_exposure_first", "Exposure First" in executive)

    # Validate the actual support packet, not only the contract declaration.
    share = build_share_report(report)
    check("share_built", isinstance(share, dict))
    if isinstance(share, dict):
        size = _int((share.get("export_meta") or {}).get("share_report_bytes_estimate"), 0)
        check("share_hard_bound", size <= SHARE_HARD_BYTES)
        check("share_target_bound", size <= SHARE_TARGET_BYTES, "warning")
        check("share_version_identity", share.get("version") == VERSION)
        share_product = share.get("product_intelligence") or {}
        share_sec = share_product.get("security") or {}
        share_maint = share_product.get("maintenance") or {}
        check("share_security_identity", _int(share_sec.get("active_secret_hint_count")) == active)
        check("share_missing_ref_identity", _int(share_maint.get("missing_reference_count")) == missing)
        if _int(controller.get("physical_pair_count")):
            check("share_controller_evidence_preserved", bool((share.get("controller_evidence") or {}).get("items")))
        rec_items = ((share.get("resilience") or {}).get("recommendations") or {}).get("items") or []
        if _int(resilience.get("must_fix_count")):
            check("share_resilience_trace_preserved", any(x.get("risky_automations") for x in rec_items if isinstance(x, dict)))

    status = "fail" if failures else ("warning" if warnings else "pass")
    result = {
        "model": SELF_CHECK_MODEL,
        "version": VERSION,
        "status": status,
        "check_count": check_count,
        "pass_count": max(0, check_count - len(failures) - len(warnings)),
        "warning_count": len(warnings),
        "failure_count": len(failures),
        "failures": failures[:40],
        "warnings": warnings[:40],
        "blocks_publication": bool(failures),
        "export_self_validated": True,
        "read_only": True,
    }
    report["self_check"] = result
    report.setdefault("diagnostic_engine", {})["report_self_check_v3"] = True
    report.setdefault("privacy", {})["self_check_v3_additional_state_reads"] = 0
    return result
