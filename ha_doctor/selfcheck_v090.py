"""Internal contract checks for HA Doctor 0.9 reports.

The self-check inspects only the report already produced by HA Doctor. It never
reads Home Assistant itself and therefore cannot create a second state snapshot.
"""
import json
from collections import Counter

VERSION = "0.9.0"
MODEL = "report_self_check_v1"


def _check(name, ok, failures, warnings, severity="fail", detail=None):
    if ok:
        return
    target = failures if severity == "fail" else warnings
    target.append({"key": name, "detail": detail or name})


def _bounded_number(value, low=0, high=100):
    try:
        value = float(value)
        return low <= value <= high
    except Exception:
        return False


def _priority_counts(items):
    counts = Counter(str(item.get("priority") or "info") for item in items if isinstance(item, dict))
    return {key: counts.get(key, 0) for key in ("action_now", "verify", "optimize")}


def run_self_check(report):
    failures = []
    warnings = []
    if not isinstance(report, dict):
        return {
            "model": MODEL, "version": VERSION, "status": "fail",
            "pass_count": 0, "warning_count": 0, "failure_count": 1,
            "failures": [{"key": "report_type", "detail": "Le rapport n'est pas un objet."}],
            "warnings": [],
        }

    findings = [x for x in report.get("findings") or [] if isinstance(x, dict)]
    plan = report.get("action_plan") or {}
    actions = [x for x in plan.get("items") or [] if isinstance(x, dict)]
    scores = report.get("scores") or {}
    severity = report.get("severity_counts") or {}
    sem = report.get("condition_semantics") or {}
    controller = report.get("controller_review_summary") or {}
    resilience = report.get("resilience_analysis") or {}
    flow = report.get("flow_confidence") or {}
    temporal = report.get("temporal_analysis") or {}
    privacy = report.get("privacy") or {}
    inventory = report.get("inventory") or {}
    schema = report.get("report_schema") or {}
    doctor = report.get("doctor_view") or {}
    triage = report.get("triage_board") or {}

    checks_before = 0
    def check(name, ok, severity_level="fail", detail=None):
        nonlocal checks_before
        checks_before += 1
        _check(name, bool(ok), failures, warnings, severity_level, detail)

    check("product_identity", str(report.get("product") or "HA Doctor") == "HA Doctor")
    check("version_identity", str(report.get("version") or "") == VERSION)
    check("report_schema_identity", str(schema.get("version") or "") == "ha-doctor-report/0.9")
    check("generated_at_present", bool(report.get("generated_at")))
    check("global_score_bounds", _bounded_number(scores.get("global")))
    for domain, value in (scores.get("domains") or {}).items():
        check(f"domain_score_bounds:{domain}", _bounded_number(value))

    actual_severity = Counter(str(item.get("severity") or "info") for item in findings)
    for key in ("critical", "high", "medium", "low", "info"):
        check(
            f"severity_count:{key}",
            int(severity.get(key, 0) or 0) == actual_severity.get(key, 0),
            "warning",
            "Le compteur de sévérité diffère de la liste de findings.",
        )

    finding_ids = [str(item.get("rule_id")) for item in findings if item.get("rule_id")]
    action_ids = [str(item.get("id")) for item in actions if item.get("id")]
    check("finding_rule_ids_unique", len(finding_ids) == len(set(finding_ids)))
    check("action_ids_present", len(action_ids) == len(actions))
    check("action_ids_unique", len(action_ids) == len(set(action_ids)))
    check("action_plan_total", int(plan.get("total", len(actions)) or 0) == len(actions))
    check("action_plan_counts", dict(plan.get("counts") or {}) == _priority_counts(actions))

    diagnostic = report.get("diagnostic_summary") or {}
    check("diagnostic_plan_id_count", int(diagnostic.get("plan_id_count", len(actions)) or 0) == len(actions))

    unproven = [x for x in sem.get("unproven_pairs") or [] if isinstance(x, dict)]
    unproven_entities = {str(x.get("entity_id")) for x in unproven if x.get("entity_id")}
    check("condition_unproven_count", int(sem.get("unproven_pair_count", len(unproven)) or 0) == len(unproven))
    check("controller_pair_identity", int(controller.get("pair_count", len(unproven)) or 0) == len(unproven))
    check("controller_entity_identity", int(controller.get("entity_count", len(unproven_entities)) or 0) == len(unproven_entities))

    external = [x for x in resilience.get("items") or [] if isinstance(x, dict) and x.get("counts_as_external_spof")]
    for status in ("protected", "partial", "review"):
        key = f"{status}_count"
        check(
            f"resilience_{status}_identity",
            int(resilience.get(key, 0) or 0) == sum(1 for x in external if str(x.get("status")) == status),
        )

    for key in ("target_resolution_rate", "dynamic_target_resolution_rate", "review_required_ratio", "low_confidence_ratio"):
        if key in flow:
            check(f"flow_rate_bounds:{key}", _bounded_number(flow.get(key), 0, 1))
    check("flow_unresolved_nonnegative", int(flow.get("unresolved_dynamic_targets", 0) or 0) >= 0)

    for key in ("new_count", "persistent_count", "recurrent_count", "resolved_since_previous_count", "deescalated_since_previous_count"):
        if key in temporal:
            check(f"temporal_nonnegative:{key}", int(temporal.get(key, 0) or 0) >= 0)

    for key in ("states", "unavailable_count", "unknown_count", "yaml_files_scanned", "automations_detected"):
        if key in inventory:
            check(f"inventory_nonnegative:{key}", int(inventory.get(key, 0) or 0) >= 0)

    check("privacy_no_automatic_changes", not bool(privacy.get("automatic_configuration_changes", False)))
    check("privacy_product_no_raw_states", not bool(privacy.get("product_layer_raw_states_persisted", False)))
    check("privacy_product_no_raw_yaml", not bool(privacy.get("product_layer_raw_yaml_persisted", False)))
    check("privacy_product_no_secrets", not bool(privacy.get("product_layer_secret_values_persisted", False)))
    check("product_no_additional_state_reads", int(privacy.get("product_layer_additional_state_reads", 0) or 0) == 0)

    preview = report.get("score_v5_preview") or {}
    if preview:
        check("score_v5_not_primary", not bool(preview.get("applied_to_primary_score", False)))
    check("doctor_view_present", bool(doctor and doctor.get("model")))
    check("triage_board_present", bool(triage and triage.get("model")))
    check("triage_total_identity", int(triage.get("total", len(actions)) or 0) == len(actions))
    triage_ids = [str(x.get("id")) for x in triage.get("items") or [] if isinstance(x, dict) and x.get("id")]
    check("triage_action_identity", set(triage_ids) == set(action_ids))

    consistency = report.get("consistency_analysis") or {}
    check("legacy_consistency_not_failed", str(consistency.get("status") or "pass") != "fail", "warning")

    try:
        encoded = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        check("report_json_serializable", True)
        check("report_contains_no_nul", b"\x00" not in encoded)
        check("report_size_sane", len(encoded) < 5_000_000, "warning", "Rapport local supérieur à 5 Mo.")
        report_bytes = len(encoded)
    except Exception as exc:
        check("report_json_serializable", False, "fail", type(exc).__name__)
        report_bytes = None

    status = "fail" if failures else ("warning" if warnings else "pass")
    pass_count = max(0, checks_before - len(failures) - len(warnings))
    result = {
        "model": MODEL,
        "version": VERSION,
        "status": status,
        "check_count": checks_before,
        "pass_count": pass_count,
        "warning_count": len(warnings),
        "failure_count": len(failures),
        "failures": failures[:20],
        "warnings": warnings[:20],
        "report_bytes": report_bytes,
        "blocks_publication": bool(failures),
        "read_only": True,
    }
    report["self_check"] = result
    report.setdefault("diagnostic_engine", {})["report_self_check_v1"] = True
    report.setdefault("privacy", {})["self_check_additional_state_reads"] = 0
    return result
