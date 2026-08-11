"""HA Doctor 0.17 compact support export focused on resolution evidence."""

import json
from contracts_v170 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
)

MODEL = SHARE_MODEL
SCHEMA = SHARE_SCHEMA
TARGET_BYTES = SHARE_TARGET_BYTES
HARD_BYTES = SHARE_HARD_BYTES


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))


def _pick(obj, keys):
    return {k: obj.get(k) for k in keys if k in obj}


def _findings(report):
    return [_pick(x, ("rule_id", "title", "severity", "domain", "priority")) for x in report.get("findings") or [] if isinstance(x, dict)]


def _actions(report):
    rows = []
    for x in (report.get("action_plan") or {}).get("items") or []:
        if not isinstance(x, dict): continue
        dep = x.get("dependency_impact") or {}
        row = _pick(x, (
            "id", "title", "priority", "severity", "domain", "confidence", "source_type", "source_id",
            "operational_lane", "operational_relevance", "resolution_status",
        ))
        row["impact"] = _pick(dep, ("model", "level", "impacted_automation_count", "target_entities", "scope", "phase_aware"))
        if x.get("feedback_resolution"):
            row["feedback"] = _pick(x.get("feedback_resolution") or {}, ("review_count", "statically_resolved_count", "terminating_transition_count"))
        if x.get("missing_reference_resolution"):
            row["references"] = _pick(x.get("missing_reference_resolution") or {}, ("runtime_relevant_count", "low_impact_count", "archive_or_inactive_count"))
        if x.get("resilience_resolution"):
            row["resilience"] = _pick(x.get("resilience_resolution") or {}, ("must_fix_count", "hardening_count"))
        rows.append(row)
    return rows


def _controller(report):
    sem = report.get("condition_semantics") or {}
    reviews = []
    for pair in sem.get("unproven_pairs") or []:
        if not isinstance(pair, dict): continue
        row = _pick(pair, ("entity_id", "automations", "target_kind", "review_priority"))
        event = pair.get("v10_event_analysis") or pair.get("event_analysis") or {}
        if event and pair.get("target_kind") == "actuator":
            conflicts = []
            for c in event.get("conflicts") or []:
                if not isinstance(c, dict): continue
                conflicts.append(_pick(c, ("intent_a", "intent_b", "trigger_a", "trigger_b", "event_kind", "overlap_evidence", "retrigger_requires_boundary_recross")))
            row["event_analysis"] = {
                "status": event.get("status"), "crossing_event_conflict_count": event.get("crossing_event_conflict_count", 0),
                "conflicts": conflicts[:2], "simultaneous_execution_proven": False, "continuous_conflict_proven": False,
            }
        reviews.append(row)
    impact = report.get("controller_impact") or {}
    return {
        "model": sem.get("model"), "controller_pairs_analyzed": sem.get("controller_pairs_analyzed", 0),
        "resolved_pair_count": sem.get("resolved_pair_count", 0), "physical_unproven_pair_count": sem.get("physical_unproven_pair_count", 0),
        "helper_unproven_pair_count": sem.get("helper_unproven_pair_count", 0),
        "impact": _pick(impact, ("model", "scope", "physical_pair_count", "impacted_automation_count", "impacted_automations", "target_entities", "level")),
        "review_items": reviews[:4],
    }


def _resilience(report):
    recs = report.get("resilience_recommendations") or {}
    items = []
    for x in recs.get("items") or []:
        if not isinstance(x, dict): continue
        row = _pick(x, ("entity_id", "tier", "criticality", "risky_automations", "pre_control_risk_count", "weak_pre_control_risk_count", "phase_adjustment", "resolution_status"))
        guard = x.get("guard_strategy") or {}
        if guard:
            row["guard"] = _pick(guard, ("strategy", "recommended_conditions", "safe_failure_policy", "automatic_change"))
        items.append(row)
    return {
        "model": recs.get("model"), "analysis_model": recs.get("analysis_model"), "count": recs.get("count", 0),
        "must_fix_count": recs.get("must_fix_count", 0), "hardening_count": recs.get("hardening_count", 0), "items": items[:4],
    }


def _automation_resolution(report):
    feedback = report.get("automation_feedback_semantics") or {}
    duplicate = report.get("duplicate_action_semantics") or {}
    return {
        "model": (report.get("automation_resolution") or {}).get("model"),
        "feedback": _pick(feedback, (
            "model", "count", "state_reassertion_count", "terminating_transition_count", "self_retrigger_candidate_count",
            "reentry_candidate_count", "review_count", "statically_resolved_count", "runtime_loop_proven_count",
        )),
        "duplicate": _pick(duplicate, (
            "model", "count", "side_effect_duplicate_count", "manual_fix_ready_count", "automatic_cleanup",
        )),
    }


def _references(report):
    refs = report.get("missing_reference_intelligence") or {}
    items = []
    for x in refs.get("items") or []:
        if isinstance(x, dict):
            items.append(_pick(x, ("entity_id", "source", "classification", "review_priority", "replacement_inferred")))
    return {
        "model": refs.get("model"), "finding_present": refs.get("finding_present"),
        "evidence_entity_count": refs.get("evidence_entity_count", 0), "runtime_relevant_count": refs.get("runtime_relevant_count", 0),
        "low_impact_count": refs.get("low_impact_count", 0), "archive_or_inactive_count": refs.get("archive_or_inactive_count", 0),
        "replacement_inference_enabled": False, "items": items[:10],
    }


def _temporal(report):
    t = report.get("temporal_analysis") or {}
    attr = report.get("score_attribution") or t.get("score_attribution") or {}
    return {
        **_pick(t, (
            "model", "history_contract", "history_policy", "publication_model", "score_comparison_status", "comparison_status",
            "previous_score", "previous_score_trusted", "current_primary_score", "score_delta",
            "latest_published_baseline_generated_at", "latest_published_baseline_score", "latest_published_baseline_report_version",
            "current_committed_baseline", "canonical_published_including_current", "next_scan_baseline_candidate_score",
            "current_snapshot_publication_complete", "current_domain_scores_persisted",
        )),
        "score_attribution": _pick(attr, (
            "model", "status", "domain_detail_available", "primary_score", "previous_primary_score", "primary_delta",
            "changed_domains", "inventory_delta", "largest_positive_domain", "largest_negative_domain", "note",
        )),
    }


def _decision(report):
    d = report.get("decision_engine") or {}
    return {
        "model": d.get("model"), "total": d.get("total", 0), "primary_action_count": d.get("primary_action_count", 0),
        "lane_counts": d.get("lane_counts") or {}, "resolution_counts": d.get("resolution_counts") or {},
        "resolution_engine": d.get("resolution_engine") or {},
        "canonical_order": {"model": (d.get("canonical_order") or {}).get("model"), "preserved_by_action_plan_order": True},
        "automatic_fix": False, "read_only": True,
    }


def build_share_report(report):
    diagnostic = report.get("diagnostic_summary") or {}; action = report.get("action_plan") or {}
    product = report.get("product_intelligence") or {}; doctor = report.get("doctor_view") or {}; quality = report.get("quality_gates") or {}
    inventory = report.get("inventory_summary") or report.get("inventory") or {}
    trust = doctor.get("trust") or report.get("diagnostic_trust") or {}
    payload = {
        "product": "HA Doctor", "version": VERSION, "generated_at": report.get("generated_at"),
        "scan_duration_seconds": report.get("scan_duration_seconds"), "scores": report.get("scores") or {},
        "severity_counts": report.get("severity_counts") or {},
        "share_schema": {"version": SCHEMA, "model": MODEL, "source_report_version": VERSION, "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES},
        "inventory_summary": _pick(inventory, ("states", "unavailable_count", "unknown_count", "yaml_files_scanned", "yaml_bytes_scanned", "automations_detected", "blueprints_detected", "entity_references_detected")),
        "diagnostic_summary": _pick(diagnostic, ("operational_counts", "actionable_count", "headline", "source", "plan_id_count", "resolution", "top_actions")),
        "executive_summary": _pick(report.get("executive_summary") or {}, ("health_score", "health_label", "complexity_score", "complexity_label", "score_v5_preview", "projected_after_top_3_fixes", "score_attribution", "resolution_summary")),
        "findings": _findings(report),
        "action_plan": {"model": action.get("model"), "total": action.get("total", 0), "items": _actions(report)},
        "controller": _controller(report), "resilience": _resilience(report),
        "automation_resolution": _automation_resolution(report), "missing_references": _references(report),
        "decision_engine": _decision(report), "temporal_truth": _temporal(report),
        "quality_gates": {"model": quality.get("model"), "overall": quality.get("overall"), "counts": quality.get("counts") or {}, "non_pass_gates": quality.get("non_pass_gates") or []},
        "doctor_view": {
            "model": doctor.get("model"), "verdict": doctor.get("verdict") or {}, "technical_health_score": doctor.get("technical_health_score"),
            "trust": _pick(trust, ("model", "score", "level", "read_only", "single_snapshot_evidence", "public_contract_truth", "self_check_status", "final_export_self_validated", "temporal_score_comparison_status", "score_attribution_status", "current_committed_baseline", "canonical_published_including_current")),
            "decision_summary": doctor.get("decision_summary") or {},
        },
        "self_check": _pick(report.get("self_check") or {}, ("model", "version", "status", "check_count", "pass_count", "warning_count", "failure_count", "failures", "warnings", "blocks_publication", "final_export_self_validated", "final_export_bytes")),
        "product_intelligence": {
            "model": product.get("model"), "security": product.get("security") or {},
            "automation_resolution": product.get("automation_resolution") or {},
            "public_contract_truth": _pick(product.get("public_contract_truth") or {}, ("model", "all_current_contracts_fresh", "decision_item_identity", "canonical_order_identity", "playbook_contract_fresh", "replacement_inference_disabled")),
        },
        "public_contracts": {
            "diagnostic_source": diagnostic.get("source"), "action_plan_model": action.get("model"),
            "controller_review_model": (report.get("controller_review_summary") or {}).get("model"),
            "condition_model": (report.get("condition_semantics") or {}).get("model"),
            "decision_model": (report.get("decision_engine") or {}).get("model"), "temporal_model": (report.get("temporal_analysis") or {}).get("model"),
            "share_schema": SHARE_SCHEMA,
        },
        "report_schema": {"version": REPORT_SCHEMA, "capabilities_count": len((report.get("report_schema") or {}).get("capabilities") or [])},
    }
    meta = {
        "type": MODEL, "intended_for": "assistant_or_support_analysis", "detail_level": "resolution_attribution",
        "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES, "contract_source": "contracts_v170",
        "raw_states_included": False, "raw_yaml_included": False, "secret_values_included": False,
        "full_dependency_graph_included": False, "entity_ids_preserved": True,
        "source_finding_count": len(report.get("findings") or []), "exported_finding_count": len(payload["findings"]),
        "source_action_count": len(action.get("items") or []), "exported_action_count": len(payload["action_plan"]["items"]),
        "all_action_identities_preserved": True, "all_finding_identities_preserved": True,
        "resolution_evidence_preserved": True, "score_attribution_preserved": True,
        "controller_exact_scope_preserved": True, "resilience_guard_strategy_preserved": True,
        "replacement_inference_disabled": True, "published_baseline_visibility_preserved": True,
    }
    payload["export_meta"] = meta

    # Progressive compaction never removes finding/action identities.
    if _size(payload) > TARGET_BYTES:
        payload["missing_references"]["items"] = payload["missing_references"].get("items", [])[:5]
        payload["controller"]["review_items"] = payload["controller"].get("review_items", [])[:2]
        payload["product_intelligence"].pop("security", None)
    if _size(payload) > TARGET_BYTES:
        for row in payload["action_plan"]["items"]:
            if row.get("operational_lane") in {"watch", "optimize"}:
                row.pop("impact", None)
        payload["doctor_view"].pop("decision_summary", None)
    if _size(payload) > TARGET_BYTES:
        payload["missing_references"].pop("items", None)
        payload["controller"]["review_items"] = payload["controller"].get("review_items", [])[:1]
    if _size(payload) > HARD_BYTES:
        payload.pop("product_intelligence", None)
        payload["resilience"]["items"] = payload["resilience"].get("items", [])[:2]

    meta["share_report_bytes_estimate"] = _size(payload)
    meta["within_target_bytes"] = meta["share_report_bytes_estimate"] <= TARGET_BYTES
    meta["within_hard_bytes"] = meta["share_report_bytes_estimate"] <= HARD_BYTES
    return payload


def build_markdown_summary(report):
    d = report.get("decision_engine") or {}; t = report.get("temporal_analysis") or {}; attr = report.get("score_attribution") or {}
    res = d.get("resolution_counts") or {}; lanes = d.get("lane_counts") or {}
    lines = [
        f"# HA Doctor {VERSION}", "", f"Score : {(report.get('scores') or {}).get('global','—')}/100", "",
        "## Résolution", "",
        f"- Corrections prêtes : {res.get('manual_fix_ready',0)}", f"- Revues logiques : {res.get('logic_review_required',0)}",
        f"- Résolues statiquement : {res.get('statically_resolved',0)}", f"- Surveillance : {lanes.get('watch',0)}", "",
        "## Score", "", f"- Comparaison : {t.get('score_comparison_status', t.get('comparison_status','—'))}",
        f"- Attribution : {attr.get('status','—')}", f"- Delta : {attr.get('primary_delta','—')}", "",
        "HA Doctor reste strictement en lecture seule.", "",
    ]
    return "\n".join(lines)
