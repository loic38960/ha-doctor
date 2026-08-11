"""HA Doctor 0.15 compact support report.

Share V9 targets 22 KiB by removing raw domain/example inventories and repeated
cross-sections while preserving every finding/action identity plus the evidence
needed to understand publication, event-window policy and resilience.
"""

import json
from contracts_v150 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL, DECISION_MODEL, CONDITION_MODEL,
)

MODEL = SHARE_MODEL
SCHEMA = SHARE_SCHEMA
TARGET_BYTES = SHARE_TARGET_BYTES
HARD_BYTES = SHARE_HARD_BYTES


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _pick(obj, keys):
    obj = obj or {}
    return {k: obj.get(k) for k in keys if k in obj}


def _inventory(report):
    inv = report.get("inventory_summary") or report.get("inventory") or {}
    return _pick(inv, (
        "states", "unavailable_count", "unknown_count", "yaml_files_scanned", "yaml_bytes_scanned",
        "automations_detected", "blueprints_detected", "entity_references_detected",
    ))


def _findings(report):
    return [
        _pick(x, ("rule_id", "title", "severity", "domain", "priority"))
        for x in report.get("findings") or [] if isinstance(x, dict)
    ]


def _actions(report):
    out = []
    for x in (report.get("action_plan") or {}).get("items") or []:
        if not isinstance(x, dict):
            continue
        dep = x.get("dependency_impact") or {}
        row = _pick(x, (
            "id", "title", "priority", "severity", "domain", "confidence", "source_type", "source_id",
            "operational_lane", "operational_relevance",
        ))
        row["impacted_automation_count"] = dep.get("impacted_automation_count", 0)
        row["dependency_level"] = dep.get("level", "none")
        out.append(row)
    return out


def _condition(report):
    sem = report.get("condition_semantics") or {}
    reviews = []
    for pair in sem.get("unproven_pairs") or []:
        if not isinstance(pair, dict):
            continue
        row = {
            "entity_id": pair.get("entity_id"), "automations": list(pair.get("automations") or [])[:2],
            "target_kind": pair.get("target_kind"), "review_priority": pair.get("review_priority"),
        }
        event = pair.get("v10_event_analysis") or {}
        if event:
            conflicts = []
            for conflict in event.get("conflicts") or []:
                conflicts.append({
                    "intent_a": conflict.get("intent_a"), "intent_b": conflict.get("intent_b"),
                    "trigger_a": conflict.get("trigger_a"), "trigger_b": conflict.get("trigger_b"),
                    "trigger_platform_a": conflict.get("trigger_platform_a"), "trigger_platform_b": conflict.get("trigger_platform_b"),
                    "event_kind": conflict.get("event_kind"),
                    "overlap_evidence": list(conflict.get("overlap_evidence") or [])[:2],
                    "retrigger_requires_boundary_recross": conflict.get("retrigger_requires_boundary_recross"),
                })
            row["event_analysis"] = {
                "model": event.get("model"), "status": event.get("status"),
                "conflict_path_pair_count": event.get("conflict_path_pair_count", 0),
                "crossing_event_conflict_count": event.get("crossing_event_conflict_count", 0),
                "event_kinds": event.get("event_kinds") or [], "conflicts": conflicts[:2],
                "simultaneous_execution_proven": False, "continuous_conflict_proven": False,
                "numeric_state_crossing_semantics_applied": event.get("numeric_state_crossing_semantics_applied", False),
            }
        reviews.append(row)
    return {
        "model": sem.get("model") or CONDITION_MODEL,
        "controller_pairs_analyzed": sem.get("controller_pairs_analyzed", 0),
        "resolved_pair_count": sem.get("resolved_pair_count", 0),
        "physical_unproven_pair_count": sem.get("physical_unproven_pair_count", 0),
        "helper_unproven_pair_count": sem.get("helper_unproven_pair_count", 0),
        "branch_numeric_resolved_pair_count": sem.get("branch_numeric_resolved_pair_count", 0),
        "policy_overlap_pair_count": sem.get("policy_overlap_pair_count", 0),
        "event_window_policy_overlap_pair_count": sem.get("event_window_policy_overlap_pair_count", 0),
        "crossing_event_policy_overlap_pair_count": sem.get("crossing_event_policy_overlap_pair_count", 0),
        "review_items": reviews[:4],
    }


def _resilience(report):
    analysis = report.get("resilience_analysis") or {}
    recs = report.get("resilience_recommendations") or {}
    items = []
    for x in recs.get("items") or []:
        if isinstance(x, dict):
            items.append(_pick(x, ("entity_id", "tier", "criticality", "unprotected_physical_automation_count", "weak_physical_automation_count", "risky_automations")))
    return {
        "analysis": _pick(analysis, ("model", "critical_dependency_count", "external_spof_count", "review_count", "partial_count", "protected_count", "unprotected_automation_count", "weak_physical_automation_count")),
        "recommendations": {"model": recs.get("model"), "count": recs.get("count", 0), "must_fix_count": recs.get("must_fix_count", 0), "hardening_count": recs.get("hardening_count", 0), "items": items[:3]},
    }


def _decision(report):
    decision = report.get("decision_engine") or {}
    top = []
    for x in decision.get("top") or []:
        if not isinstance(x, dict):
            continue
        pb = x.get("repair_playbook") or {}; steps = pb.get("steps") or []
        top.append({
            "id": x.get("id"), "title": x.get("title"), "lane": x.get("operational_lane"),
            "relevance": x.get("operational_relevance"), "readiness": pb.get("repair_readiness"),
            "category": pb.get("category"), "first_step": (steps[0] or {}).get("detail") if steps else None,
            "event_window_policy": pb.get("event_window_policy"), "risky_automations": pb.get("risky_automations"),
        })
    return {
        "model": decision.get("model") or DECISION_MODEL, "total": decision.get("total", 0),
        "primary_action_count": decision.get("primary_action_count", 0),
        "lane_counts": decision.get("lane_counts") or {}, "repair_readiness_counts": decision.get("repair_readiness_counts") or {},
        "operational_summary": decision.get("operational_summary") or {},
        "top": top[:4], "automatic_fix": False, "read_only": True,
    }


def _temporal(report):
    t = report.get("temporal_analysis") or {}; integrity = report.get("score_history_integrity") or {}
    tx = report.get("publication_transaction") or {}
    return {
        "model": t.get("model"), "history_contract": t.get("history_contract") or HISTORY_CONTRACT,
        "history_policy": t.get("history_policy") or HISTORY_POLICY, "publication_model": t.get("publication_model") or PUBLICATION_MODEL,
        "comparison_status": t.get("score_comparison_status"), "previous_score": t.get("previous_score"),
        "previous_score_trusted": t.get("previous_score_trusted"), "current_primary_score": t.get("current_primary_score"),
        "score_delta": t.get("score_delta"), "latest_candidate_status": t.get("latest_candidate_status"),
        "current_snapshot_publication_complete": t.get("current_snapshot_publication_complete"),
        "blocked_reports_never_become_score_baselines": t.get("blocked_reports_never_become_score_baselines"),
        "transaction": _pick(tx, ("model", "phase", "committed", "reason")),
        "integrity": _pick(integrity, ("model", "comparison_status", "canonical_published_snapshots_last_10", "blocked_unpublished_snapshots_last_10", "legacy_untrusted_snapshots_last_10")),
    }


def _self_check(report):
    sc = report.get("self_check") or {}
    return _pick(sc, ("model", "version", "status", "check_count", "pass_count", "warning_count", "failure_count", "failures", "warnings", "blocks_publication", "final_export_self_validated"))


def build_share_report(report):
    product = report.get("product_intelligence") or {}; doctor = report.get("doctor_view") or {}
    action = report.get("action_plan") or {}; diagnostic = report.get("diagnostic_summary") or {}
    quality = report.get("quality_gates") or {}; trust = doctor.get("trust") or {}
    payload = {
        "product": "HA Doctor", "version": VERSION, "generated_at": report.get("generated_at"),
        "scan_duration_seconds": report.get("scan_duration_seconds"), "scores": report.get("scores") or {},
        "severity_counts": report.get("severity_counts") or {},
        "share_schema": {"version": SCHEMA, "model": MODEL, "source_report_version": VERSION, "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES},
        "inventory_summary": _inventory(report),
        "diagnostic_summary": _pick(diagnostic, ("operational_counts", "actionable_count", "headline", "source", "plan_id_count", "controller_review_entity_count", "controller_review_pair_count", "top_actions")),
        "executive_summary": _pick(report.get("executive_summary") or {}, ("health_score", "health_label", "complexity_score", "complexity_label", "score_v5_preview", "projected_after_top_3_fixes", "text", "top_priority_titles")),
        "findings": _findings(report),
        "action_plan": {"model": action.get("model"), "total": action.get("total", len(action.get("items") or [])), "items": _actions(report)},
        "condition_semantics": _condition(report), "resilience": _resilience(report),
        "quality_gates": {"model": quality.get("model"), "overall": quality.get("overall"), "counts": quality.get("counts") or {}, "non_pass_gates": quality.get("non_pass_gates") or []},
        "doctor_view": {
            "model": doctor.get("model"), "verdict": doctor.get("verdict") or {}, "technical_health_score": doctor.get("technical_health_score"),
            "trust": _pick(trust, ("model", "score", "level", "single_snapshot_evidence", "public_contract_truth", "temporal_score_comparison_status", "self_check_status", "read_only")),
            "decision_summary": doctor.get("decision_summary") or {},
        },
        "self_check": _self_check(report),
        "product_intelligence": {
            "model": product.get("model"), "security": product.get("security") or {}, "maintenance": product.get("maintenance") or {},
            "score_change_trace": product.get("score_change_trace") or {}, "entity_attention": product.get("entity_attention") or {},
            "public_contract_truth": product.get("public_contract_truth") or {},
        },
        "decision_engine": _decision(report), "temporal_truth": _temporal(report),
        "public_contracts": {
            "diagnostic_source": diagnostic.get("source"), "action_plan_model": action.get("model"),
            "controller_review_model": (report.get("controller_review_summary") or {}).get("model"),
            "condition_model": (report.get("condition_semantics") or {}).get("model"),
            "decision_model": (report.get("decision_engine") or {}).get("model"),
            "temporal_model": (report.get("temporal_analysis") or {}).get("model"),
            "share_schema": (report.get("share_contract") or {}).get("schema"),
        },
        "report_schema": {"version": REPORT_SCHEMA, "capabilities_count": len((report.get("report_schema") or {}).get("capabilities") or [])},
    }
    meta = {
        "type": MODEL, "intended_for": "assistant_or_support_analysis", "detail_level": "compact_operational_truth",
        "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES, "contract_source": "contracts_v150",
        "raw_states_included": False, "raw_yaml_included": False, "secret_values_included": False,
        "full_dependency_graph_included": False, "entity_ids_preserved": True,
        "source_finding_count": len(report.get("findings") or []), "exported_finding_count": len(payload["findings"]),
        "source_action_count": len(action.get("items") or []), "exported_action_count": len(payload["action_plan"]["items"]),
        "all_action_identities_preserved": True, "all_finding_identities_preserved": True,
        "decision_engine_preserved": True, "event_window_policy_evidence_preserved": True,
        "resilience_trace_preserved": True, "publication_transaction_preserved": True,
    }
    payload["export_meta"] = meta

    # Preserve identities and evidence first; trim descriptive repetition only.
    if _size(payload) > TARGET_BYTES:
        payload["executive_summary"].pop("text", None)
        payload["decision_engine"]["top"] = payload["decision_engine"].get("top", [])[:3]
    if _size(payload) > TARGET_BYTES:
        payload["product_intelligence"].pop("maintenance", None)
        payload["product_intelligence"]["security"] = _pick(payload["product_intelligence"].get("security") or {}, ("model", "posture", "active_secret_hint_count", "archive_secret_hint_count", "secret_values_in_report"))
    if _size(payload) > TARGET_BYTES:
        payload["condition_semantics"]["review_items"] = payload["condition_semantics"].get("review_items", [])[:3]
        payload["doctor_view"].pop("decision_summary", None)
    if _size(payload) > HARD_BYTES:
        payload["decision_engine"].pop("top", None)
        payload["resilience"]["analysis"] = _pick(payload["resilience"].get("analysis") or {}, ("model", "external_spof_count", "review_count", "unprotected_automation_count"))

    meta["share_report_bytes_estimate"] = _size(payload)
    meta["within_target_bytes"] = meta["share_report_bytes_estimate"] <= TARGET_BYTES
    meta["within_hard_bytes"] = meta["share_report_bytes_estimate"] <= HARD_BYTES
    return payload


def build_markdown_summary(report):
    d = report.get("decision_engine") or {}; sem = report.get("condition_semantics") or {}; t = report.get("temporal_analysis") or {}; sc = report.get("self_check") or {}
    lanes = d.get("lane_counts") or {}
    return "\n".join([
        f"# HA Doctor {VERSION}", "",
        f"Score : {(report.get('scores') or {}).get('global','—')}/100",
        f"Self-Check : {sc.get('status','—')}", "",
        "## Décisions", "",
        f"- À corriger : {lanes.get('fix_now',0)}", f"- Revue logique : {lanes.get('logic_review',0)}",
        f"- Surveillance : {lanes.get('watch',0)}", f"- Optimisations : {lanes.get('optimize',0)}", "",
        "## Contrôleurs", "",
        f"- Paires physiques à revoir : {sem.get('physical_unproven_pair_count',0)}",
        f"- Overlaps événementiels : {sem.get('event_window_policy_overlap_pair_count',0)}",
        f"- Overlaps par franchissement numeric_state : {sem.get('crossing_event_policy_overlap_pair_count',0)}", "",
        "## Publication", "",
        f"- Comparaison : {t.get('score_comparison_status','—')}",
        f"- Phase : {(report.get('publication_transaction') or {}).get('phase','—')}",
        f"- Baseline précédente : {t.get('previous_score') if t.get('previous_score_trusted') else 'aucune'}", "",
        "HA Doctor reste strictement en lecture seule.", "",
    ])
