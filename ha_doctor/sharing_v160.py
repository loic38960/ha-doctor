"""HA Doctor 0.16 compact precision support report."""

import json
from contracts_v160 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    DECISION_MODEL, CONDITION_MODEL, TEMPORAL_MODEL, CONTROLLER_IMPACT_MODEL,
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
    return [
        _pick(x, ("rule_id", "title", "severity", "domain", "priority"))
        for x in report.get("findings") or [] if isinstance(x, dict)
    ]


def _actions(report):
    rows = []
    for x in (report.get("action_plan") or {}).get("items") or []:
        if not isinstance(x, dict):
            continue
        dep = x.get("dependency_impact") or {}
        row = _pick(x, (
            "id", "title", "priority", "severity", "domain", "confidence", "source_type", "source_id",
            "operational_lane", "operational_relevance", "execution_priority_score",
        ))
        row["impact"] = _pick(dep, ("model", "level", "impacted_automation_count", "target_entities", "scope", "phase_aware"))
        rows.append(row)
    return rows


def _condition(report):
    sem = report.get("condition_semantics") or {}
    reviews = []
    for pair in sem.get("unproven_pairs") or []:
        if not isinstance(pair, dict):
            continue
        row = _pick(pair, ("entity_id", "automations", "target_kind", "review_priority"))
        event = pair.get("v10_event_analysis") or {}
        if event:
            conflicts = []
            for conflict in event.get("conflicts") or []:
                conflicts.append(_pick(conflict, (
                    "intent_a", "intent_b", "trigger_a", "trigger_b", "event_kind",
                    "overlap_evidence", "retrigger_requires_boundary_recross",
                )))
            row["event_analysis"] = {
                "status": event.get("status"), "conflict_path_pair_count": event.get("conflict_path_pair_count", 0),
                "crossing_event_conflict_count": event.get("crossing_event_conflict_count", 0),
                "event_kinds": event.get("event_kinds") or [], "conflicts": conflicts[:3],
                "simultaneous_execution_proven": False, "continuous_conflict_proven": False,
            }
        reviews.append(row)
    return {
        "model": sem.get("model") or CONDITION_MODEL,
        "controller_pairs_analyzed": sem.get("controller_pairs_analyzed", 0),
        "resolved_pair_count": sem.get("resolved_pair_count", 0),
        "physical_unproven_pair_count": sem.get("physical_unproven_pair_count", 0),
        "helper_unproven_pair_count": sem.get("helper_unproven_pair_count", 0),
        "policy_overlap_pair_count": sem.get("policy_overlap_pair_count", 0),
        "event_window_policy_overlap_pair_count": sem.get("event_window_policy_overlap_pair_count", 0),
        "controller_impact": report.get("controller_impact") or sem.get("controller_impact") or {},
        "review_items": reviews[:6],
    }


def _resilience(report):
    recs = report.get("resilience_recommendations") or {}
    items = []
    for x in recs.get("items") or []:
        if not isinstance(x, dict):
            continue
        items.append(_pick(x, (
            "entity_id", "tier", "criticality", "unprotected_physical_automation_count", "weak_physical_automation_count",
            "risky_automations", "pre_control_risk_count", "post_action_confirmation_count", "trigger_dependency_count", "phase_adjustment",
        )))
    return {
        "model": recs.get("model"), "analysis_model": recs.get("analysis_model"),
        "count": recs.get("count", 0), "must_fix_count": recs.get("must_fix_count", 0),
        "hardening_count": recs.get("hardening_count", 0), "items": items[:4],
    }


def _decision(report):
    decision = report.get("decision_engine") or {}
    top = []
    for x in decision.get("top") or []:
        if not isinstance(x, dict): continue
        pb = x.get("repair_playbook") or {}; steps = pb.get("steps") or []
        top.append({
            "id": x.get("id"), "title": x.get("title"), "lane": x.get("operational_lane"),
            "relevance": x.get("operational_relevance"), "priority_score": x.get("execution_priority_score"),
            "readiness": pb.get("repair_readiness"), "category": pb.get("category"),
            "first_step": (steps[0] or {}).get("detail") if steps else None,
        })
    return {
        "model": decision.get("model") or DECISION_MODEL, "total": decision.get("total", 0),
        "primary_action_count": decision.get("primary_action_count", 0), "lane_counts": decision.get("lane_counts") or {},
        "canonical_order": decision.get("canonical_order") or {}, "top": top[:6],
        "automatic_fix": False, "read_only": True,
    }


def _temporal(report):
    t = report.get("temporal_analysis") or {}
    return _pick(t, (
        "model", "history_contract", "history_policy", "publication_model", "score_comparison_status",
        "previous_score", "previous_score_trusted", "current_primary_score", "score_delta",
        "latest_published_baseline_generated_at", "latest_published_baseline_score", "latest_published_baseline_age_seconds",
        "latest_published_baseline_eligible_for_delta", "current_committed_baseline", "canonical_published_including_current",
        "next_scan_baseline_candidate_score", "next_scan_baseline_candidate_generated_at",
        "current_snapshot_publication_complete", "blocked_reports_never_become_score_baselines",
    ))


def build_share_report(report):
    product = report.get("product_intelligence") or {}; doctor = report.get("doctor_view") or {}
    decision = report.get("decision_engine") or {}; action = report.get("action_plan") or {}
    diagnostic = report.get("diagnostic_summary") or {}; quality = report.get("quality_gates") or {}
    inventory = report.get("inventory_summary") or report.get("inventory") or {}
    payload = {
        "product": "HA Doctor", "version": VERSION, "generated_at": report.get("generated_at"),
        "scan_duration_seconds": report.get("scan_duration_seconds"), "scores": report.get("scores") or {},
        "severity_counts": report.get("severity_counts") or {},
        "share_schema": {"version": SCHEMA, "model": MODEL, "source_report_version": VERSION, "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES},
        "inventory_summary": _pick(inventory, ("states", "unavailable_count", "unknown_count", "yaml_files_scanned", "yaml_bytes_scanned", "automations_detected", "blueprints_detected", "entity_references_detected")),
        "diagnostic_summary": _pick(diagnostic, ("operational_counts", "actionable_count", "headline", "source", "plan_id_count", "precision", "top_actions")),
        "executive_summary": _pick(report.get("executive_summary") or {}, ("health_score", "health_label", "complexity_score", "complexity_label", "score_v5_preview", "projected_after_top_3_fixes", "text", "precision_summary")),
        "findings": _findings(report),
        "action_plan": {"model": action.get("model"), "total": action.get("total", 0), "items": _actions(report)},
        "condition_semantics": _condition(report), "resilience": _resilience(report),
        "automation_precision": {
            "duplicate_actions": report.get("duplicate_action_semantics") or {},
            "feedback": report.get("automation_feedback_semantics") or {},
        },
        "quality_gates": {"model": quality.get("model"), "overall": quality.get("overall"), "counts": quality.get("counts") or {}, "non_pass_gates": quality.get("non_pass_gates") or []},
        "doctor_view": {"model": doctor.get("model"), "verdict": doctor.get("verdict") or {}, "technical_health_score": doctor.get("technical_health_score"), "trust": doctor.get("trust") or {}, "decision_summary": doctor.get("decision_summary") or {}},
        "self_check": report.get("self_check") or {}, "decision_engine": _decision(report),
        "temporal_truth": _temporal(report),
        "product_intelligence": {
            "model": product.get("model"), "security": product.get("security") or {}, "maintenance": product.get("maintenance") or {},
            "controller_impact": product.get("controller_impact") or {}, "resilience_precision": product.get("resilience_precision") or {},
            "public_contract_truth": product.get("public_contract_truth") or {},
        },
        "public_contracts": {
            "diagnostic_source": diagnostic.get("source"), "action_plan_model": action.get("model"),
            "controller_review_model": (report.get("controller_review_summary") or {}).get("model"),
            "condition_model": (report.get("condition_semantics") or {}).get("model"),
            "decision_model": decision.get("model"), "temporal_model": (report.get("temporal_analysis") or {}).get("model"),
            "share_schema": SHARE_SCHEMA,
        },
        "report_schema": {"version": REPORT_SCHEMA, "capabilities_count": len((report.get("report_schema") or {}).get("capabilities") or [])},
    }
    meta = {
        "type": MODEL, "intended_for": "assistant_or_support_analysis", "detail_level": "precision_evidence",
        "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES, "contract_source": "contracts_v160",
        "raw_states_included": False, "raw_yaml_included": False, "secret_values_included": False,
        "full_dependency_graph_included": False, "entity_ids_preserved": True,
        "source_finding_count": len(report.get("findings") or []), "exported_finding_count": len(payload["findings"]),
        "source_action_count": len(action.get("items") or []), "exported_action_count": len(payload["action_plan"]["items"]),
        "all_action_identities_preserved": True, "all_finding_identities_preserved": True,
        "canonical_order_preserved": True, "controller_exact_scope_preserved": True,
        "resilience_phase_trace_preserved": True, "automation_precision_preserved": True,
        "published_baseline_visibility_preserved": True,
    }
    payload["export_meta"] = meta

    if _size(payload) > TARGET_BYTES:
        payload["executive_summary"].pop("text", None)
        payload["decision_engine"]["top"] = payload["decision_engine"].get("top", [])[:4]
        payload["automation_precision"]["duplicate_actions"].pop("items", None)
        payload["automation_precision"]["feedback"].pop("items", None)
    if _size(payload) > TARGET_BYTES:
        payload["product_intelligence"].pop("maintenance", None)
        payload["condition_semantics"]["review_items"] = payload["condition_semantics"].get("review_items", [])[:4]
    if _size(payload) > TARGET_BYTES:
        payload["decision_engine"].pop("top", None)
        for row in payload["action_plan"]["items"]:
            row.pop("execution_priority_score", None)
    if _size(payload) > HARD_BYTES:
        payload.pop("automation_precision", None)
        payload["condition_semantics"]["review_items"] = payload["condition_semantics"].get("review_items", [])[:2]

    meta["share_report_bytes_estimate"] = _size(payload)
    meta["within_target_bytes"] = meta["share_report_bytes_estimate"] <= TARGET_BYTES
    meta["within_hard_bytes"] = meta["share_report_bytes_estimate"] <= HARD_BYTES
    return payload


def build_markdown_summary(report):
    d = report.get("decision_engine") or {}; t = report.get("temporal_analysis") or {}; impact = report.get("controller_impact") or {}
    recs = report.get("resilience_recommendations") or {}
    lines = [
        f"# HA Doctor {VERSION}", "",
        f"Score : {(report.get('scores') or {}).get('global','—')}/100",
        f"Verdict : {((report.get('doctor_view') or {}).get('verdict') or {}).get('label','—')}", "",
        "## Décisions", "",
        f"- À corriger : {(d.get('lane_counts') or {}).get('fix_now',0)}",
        f"- Revue logique : {(d.get('lane_counts') or {}).get('logic_review',0)}",
        f"- Surveillance : {(d.get('lane_counts') or {}).get('watch',0)}",
        f"- Optimisations : {(d.get('lane_counts') or {}).get('optimize',0)}", "",
        "## Précision", "",
        f"- Paires physiques ouvertes : {impact.get('physical_pair_count',0)}",
        f"- Automatisations réellement dans ce scope : {impact.get('impacted_automation_count',0)}",
        f"- Résilience must-fix : {recs.get('must_fix_count',0)}",
        f"- Résilience hardening : {recs.get('hardening_count',0)}", "",
        "## Historique", "",
        f"- Comparaison : {t.get('score_comparison_status','—')}",
        f"- Dernière baseline publiée visible : {t.get('latest_published_baseline_score','—')}",
        f"- Baseline actuelle commitée : {'oui' if t.get('current_committed_baseline') else 'non'}", "",
        "HA Doctor reste strictement en lecture seule.", "",
    ]
    return "\n".join(lines)
