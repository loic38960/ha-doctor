"""HA Doctor 0.8.8 compact assistant handoff.

Extends the proven 0.8.7 bounded export with the small V6/V4 calibration
counters. The same hard byte ceiling is preserved.
"""
import json

import sharing_v087 as base

VERSION = "0.8.8"
MODEL = base.MODEL
SCHEMA = base.SCHEMA
TARGET_BYTES = base.TARGET_BYTES
HARD_BYTES = base.HARD_BYTES


def _json_size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _pick(source, keys):
    if not isinstance(source, dict):
        return {}
    return {key: source.get(key) for key in keys if key in source}


def _add_v088_sections(payload, report):
    sem = report.get("condition_semantics") or {}
    sem_out = payload.setdefault("condition_semantics", {})
    sem_out.update(_pick(sem, (
        "semantic_v6_resolved_pair_count",
        "membership_exclusive_pair_count",
        "supervisory_interlock_pair_count",
        "mediated_interlock_pair_count",
        "pre_v6_unproven_pair_count",
        "pre_v6_physical_unproven_pair_count",
    )))

    resilience = report.get("resilience_analysis") or {}
    res_out = payload.setdefault("resilience", {}).setdefault("analysis", {})
    res_out.update(_pick(resilience, (
        "model", "protected_count", "partial_count", "review_count",
        "low_operational_exposure_count", "physical_control_consumer_count",
        "observational_consumer_count", "weak_physical_automation_count",
        "unprotected_automation_count",
    )))

    source_items = {
        str(item.get("entity_id") or ""): item
        for item in resilience.get("items") or []
        if isinstance(item, dict) and item.get("entity_id")
    }
    for exported in res_out.get("items") or []:
        if not isinstance(exported, dict):
            continue
        source = source_items.get(str(exported.get("entity_id") or "")) or {}
        exported.update(_pick(source, (
            "physical_control_consumer_count", "helper_control_consumer_count",
            "observational_consumer_count", "other_control_consumer_count",
            "unprotected_physical_automation_count", "weak_physical_automation_count",
            "protected_physical_automation_count",
        )))

    summary = report.get("controller_review_summary") or {}
    payload["controller_review_summary"] = {
        **(payload.get("controller_review_summary") or {}),
        **_pick(summary, (
            "model", "entity_count", "pair_count", "physical_pair_count",
            "helper_pair_count", "semantic_v6_resolved_pair_count",
            "membership_exclusive_pair_count", "supervisory_interlock_pair_count",
            "mediated_interlock_pair_count",
        )),
    }

    payload["version"] = VERSION
    payload.setdefault("share_schema", {}).update({
        "source_report_version": VERSION,
    })
    payload.setdefault("report_schema", {})["version"] = "ha-doctor-report/0.8.8"
    return payload


def build_share_report(report):
    if not isinstance(report, dict):
        return None
    payload = base.build_share_report(report)
    if not isinstance(payload, dict):
        return payload
    _add_v088_sections(payload, report)

    meta = payload.setdefault("export_meta", {})
    meta["type"] = MODEL
    meta["source_report_version"] = VERSION
    meta["share_report_bytes_estimate"] = _json_size(payload)

    # Preserve the established hard bound. The V6/V4 counters are valuable but
    # secondary examples can be removed before any diagnostic identity is lost.
    if _json_size(payload) > HARD_BYTES:
        sem_out = payload.get("condition_semantics") or {}
        sem_out.pop("branch_protocol_resolved_pairs", None)
        res_out = (payload.get("resilience") or {}).get("analysis") or {}
        for item in res_out.get("items") or []:
            if isinstance(item, dict):
                item.pop("helper_control_consumer_count", None)
                item.pop("other_control_consumer_count", None)
        meta["detail_level"] = "hard_bounded_v088"
        meta["v088_secondary_details_reduced"] = True
        meta["share_report_bytes_estimate"] = _json_size(payload)

    if _json_size(payload) > HARD_BYTES:
        # Reuse the same optional-section policy as 0.8.7. Never drop findings
        # or action identities to make room for calibration metadata.
        for key in ("entity_health_summary", "architecture_summary", "non_plan_observations", "score_v5_preview"):
            payload.pop(key, None)
        meta["detail_level"] = "hard_bounded_v088"
        meta["secondary_sections_omitted"] = True
        meta["share_report_bytes_estimate"] = _json_size(payload)

    return payload
