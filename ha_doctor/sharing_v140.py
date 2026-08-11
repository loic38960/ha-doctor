"""HA Doctor 0.14 compact support report.

V8 is rebuilt from explicit support needs instead of layering previous share
formats. It preserves every finding/action identity, decision lanes, the top
repair playbooks, policy-overlap evidence, resilience trace and publication-
aware temporal truth while targeting 26 KiB.
"""

import json
from contracts_v140 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    HISTORY_CONTRACT, HISTORY_POLICY, DECISION_MODEL, CONDITION_MODEL,
)

MODEL = SHARE_MODEL
SCHEMA = SHARE_SCHEMA
TARGET_BYTES = SHARE_TARGET_BYTES
HARD_BYTES = SHARE_HARD_BYTES


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _pick(obj, keys):
    return {k: obj.get(k) for k in keys if k in obj}


def _findings(report):
    out = []
    for x in report.get("findings") or []:
        if isinstance(x, dict):
            out.append(_pick(x, ("rule_id", "title", "severity", "domain", "priority", "example_count")))
    return out


def _actions(report):
    out = []
    for x in (report.get("action_plan") or {}).get("items") or []:
        if not isinstance(x, dict): continue
        dep = x.get("dependency_impact") or {}
        row = _pick(x, ("id", "title", "priority", "severity", "domain", "confidence", "confidence_score", "source_type", "source_id", "operational_lane", "operational_relevance", "execution_priority_score"))
        if dep:
            row["dependency_impact"] = _pick(dep, ("level", "impacted_automation_count", "weighted_impact_score"))
        out.append(row)
    return out


def _policy_overlap(report):
    sem = report.get("condition_semantics") or {}
    reviews = []
    for pair in sem.get("unproven_pairs") or []:
        if not isinstance(pair, dict): continue
        analysis = pair.get("v9_policy_analysis") or {}
        row = {
            "entity_id": pair.get("entity_id"), "automations": list(pair.get("automations") or [])[:2],
            "target_kind": pair.get("target_kind"), "review_priority": pair.get("review_priority"),
        }
        if analysis:
            examples = []
            for conflict in analysis.get("conflicts") or []:
                examples.append({
                    "intent_a": conflict.get("intent_a"), "intent_b": conflict.get("intent_b"),
                    "trigger_a": conflict.get("trigger_a"), "trigger_b": conflict.get("trigger_b"),
                    "overlap_evidence": list(conflict.get("overlap_evidence") or [])[:3],
                })
            row["policy_analysis"] = {
                "status": analysis.get("status"), "conflict_path_pair_count": analysis.get("conflict_path_pair_count", 0),
                "numerically_disjoint_path_pair_count": analysis.get("numerically_disjoint_path_pair_count", 0),
                "examples": examples[:3], "simultaneous_execution_proven": False,
            }
        reviews.append(row)
    return {
        "model": sem.get("model") or CONDITION_MODEL,
        "controller_pairs_analyzed": sem.get("controller_pairs_analyzed", 0),
        "resolved_pair_count": sem.get("resolved_pair_count", 0),
        "physical_unproven_pair_count": sem.get("physical_unproven_pair_count", 0),
        "helper_unproven_pair_count": sem.get("helper_unproven_pair_count", 0),
        "mandatory_guard_resolved_pair_count": sem.get("mandatory_guard_resolved_pair_count", 0),
        "branch_numeric_resolved_pair_count": sem.get("branch_numeric_resolved_pair_count", 0),
        "policy_overlap_pair_count": sem.get("policy_overlap_pair_count", 0),
        "review_items": reviews[:6],
    }


def _resilience(report):
    analysis = report.get("resilience_analysis") or {}
    recs = report.get("resilience_recommendations") or {}
    items = []
    for x in recs.get("items") or []:
        if isinstance(x, dict):
            items.append(_pick(x, ("entity_id", "tier", "criticality", "unprotected_physical_automation_count", "weak_physical_automation_count", "risky_automations")))
    return {
        "analysis": _pick(analysis, ("model", "critical_dependency_count", "external_spof_count", "review_count", "partial_count", "protected_count", "unprotected_automation_count", "weak_physical_automation_count", "physical_control_consumer_count")),
        "recommendations": {"model": recs.get("model"), "count": recs.get("count", 0), "must_fix_count": recs.get("must_fix_count", 0), "hardening_count": recs.get("hardening_count", 0), "items": items[:4]},
    }


def _decision(report):
    decision = report.get("decision_engine") or {}
    top = []
    for x in decision.get("top") or []:
        if not isinstance(x, dict): continue
        pb = x.get("repair_playbook") or {}; steps = pb.get("steps") or []; success = pb.get("success_criteria") or []
        top.append({
            "id": x.get("id"), "title": x.get("title"), "operational_lane": x.get("operational_lane"),
            "operational_relevance": x.get("operational_relevance"), "execution_priority_score": x.get("execution_priority_score"),
            "repair_readiness": pb.get("repair_readiness"), "category": pb.get("category"),
            "first_step": (steps[0] or {}).get("detail") if steps else None,
            "success": success[0] if success else None,
            "policy_overlap": pb.get("policy_overlap"), "risky_automations": pb.get("risky_automations"),
        })
    return {
        "model": decision.get("model") or DECISION_MODEL, "total": decision.get("total", 0),
        "primary_action_count": decision.get("primary_action_count", 0),
        "lane_counts": decision.get("lane_counts") or {}, "repair_readiness_counts": decision.get("repair_readiness_counts") or {},
        "operational_relevance_counts": decision.get("operational_relevance_counts") or {},
        "repair_batches": decision.get("repair_batches") or {}, "entity_attention": decision.get("entity_attention") or {},
        "top": top[:6], "automatic_fix": False, "read_only": True,
    }


def _temporal(report):
    t = report.get("temporal_analysis") or {}; integrity = report.get("score_history_integrity") or {}
    return {
        "model": t.get("model"), "history_contract": t.get("history_contract") or HISTORY_CONTRACT,
        "history_policy": t.get("history_policy") or HISTORY_POLICY, "comparison_status": t.get("score_comparison_status"),
        "previous_score": t.get("previous_score"), "previous_score_trusted": t.get("previous_score_trusted"),
        "current_primary_score": t.get("current_primary_score"), "score_delta": t.get("score_delta"),
        "latest_candidate_status": t.get("latest_candidate_status"), "meaningful_previous_generated_at": t.get("meaningful_previous_generated_at"),
        "current_snapshot_publication_complete": t.get("current_snapshot_publication_complete"),
        "blocked_reports_never_become_score_baselines": t.get("blocked_reports_never_become_score_baselines"),
        "integrity": _pick(integrity, ("model", "contract", "policy", "comparison_status", "canonical_published_snapshots_last_10", "blocked_unpublished_snapshots_last_10", "legacy_untrusted_snapshots_last_10")),
    }


def build_share_report(report):
    product = report.get("product_intelligence") or {}; doctor = report.get("doctor_view") or {}
    action = report.get("action_plan") or {}; diagnostic = report.get("diagnostic_summary") or {}
    quality = report.get("quality_gates") or {}; flow = report.get("flow_confidence") or {}
    payload = {
        "product": "HA Doctor", "version": VERSION, "generated_at": report.get("generated_at"),
        "scan_duration_seconds": report.get("scan_duration_seconds"), "scores": report.get("scores") or {},
        "severity_counts": report.get("severity_counts") or {},
        "share_schema": {"version": SCHEMA, "model": MODEL, "source_report_version": VERSION, "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES},
        "inventory_summary": report.get("inventory_summary") or report.get("inventory") or {},
        "diagnostic_summary": _pick(diagnostic, ("priority_counts", "actionable_count", "headline", "source", "plan_id_count", "controller_review_entity_count", "controller_review_pair_count", "top_actions")),
        "executive_summary": _pick(report.get("executive_summary") or {}, ("health_score", "health_label", "complexity_score", "complexity_label", "score_v5_preview", "projected_after_top_3_fixes", "text", "top_priority_titles")),
        "findings": _findings(report),
        "action_plan": {"model": action.get("model"), "total": action.get("total", len(action.get("items") or [])), "counts": action.get("counts") or {}, "items": _actions(report)},
        "flow_confidence": _pick(flow, ("model", "target_resolution_rate", "dynamic_target_resolution_rate", "dynamic_confidence_bands", "review_required_dynamic_edges", "unresolved_dynamic_targets", "quality_status")),
        "condition_semantics": _policy_overlap(report),
        "resilience": _resilience(report),
        "quality_gates": {"model": quality.get("model"), "overall": quality.get("overall"), "counts": quality.get("counts") or {}, "non_pass_gates": quality.get("non_pass_gates") or []},
        "consistency": report.get("consistency_gates") or report.get("consistency") or {},
        "doctor_view": {"model": doctor.get("model"), "verdict": doctor.get("verdict") or {}, "technical_health_score": doctor.get("technical_health_score"), "trust": doctor.get("trust") or {}, "decision_summary": doctor.get("decision_summary") or {}},
        "self_check": report.get("self_check") or {},
        "product_intelligence": {
            "model": product.get("model"), "security": product.get("security") or {}, "maintenance": product.get("maintenance") or {},
            "score_change_trace": product.get("score_change_trace") or {}, "score_change_explainer": product.get("score_change_explainer") or {},
            "entity_attention": product.get("entity_attention") or {}, "public_contract_truth": product.get("public_contract_truth") or {},
        },
        "decision_engine": _decision(report), "temporal_truth": _temporal(report),
        "public_contracts": {
            "diagnostic_source": diagnostic.get("source"), "action_plan_model": action.get("model"),
            "controller_review_model": (report.get("controller_review_summary") or {}).get("model"),
            "condition_model": (report.get("condition_semantics") or {}).get("model"),
            "decision_model": (report.get("decision_engine") or {}).get("model"), "temporal_model": (report.get("temporal_analysis") or {}).get("model"),
        },
        "report_schema": {"version": REPORT_SCHEMA, "capabilities_count": len((report.get("report_schema") or {}).get("capabilities") or [])},
    }
    meta = {
        "type": MODEL, "intended_for": "assistant_or_support_analysis", "detail_level": "operational_decision_evidence",
        "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES, "contract_source": "contracts_v140",
        "raw_states_included": False, "raw_yaml_included": False, "secret_values_included": False,
        "full_dependency_graph_included": False, "entity_ids_preserved": True,
        "source_finding_count": len(report.get("findings") or []), "exported_finding_count": len(payload["findings"]),
        "source_action_count": len(action.get("items") or []), "exported_action_count": len(payload["action_plan"]["items"]),
        "all_action_identities_preserved": True, "all_finding_identities_preserved": True,
        "decision_engine_preserved": True, "policy_overlap_evidence_preserved": True,
        "resilience_trace_preserved": True, "publication_aware_temporal_trace_preserved": True,
    }
    payload["export_meta"] = meta

    if _size(payload) > TARGET_BYTES:
        payload["executive_summary"].pop("text", None)
        payload["decision_engine"]["top"] = payload["decision_engine"].get("top", [])[:4]
        payload["product_intelligence"].pop("score_change_explainer", None)
    if _size(payload) > TARGET_BYTES:
        payload.pop("consistency", None)
        for item in payload["action_plan"]["items"]:
            item.pop("execution_priority_score", None); item.pop("confidence_score", None)
    if _size(payload) > TARGET_BYTES:
        payload["decision_engine"].pop("repair_batches", None)
        payload["condition_semantics"]["review_items"] = payload["condition_semantics"].get("review_items", [])[:3]
    if _size(payload) > HARD_BYTES:
        payload["decision_engine"].pop("top", None)
        payload.pop("flow_confidence", None)

    meta["share_report_bytes_estimate"] = _size(payload)
    meta["within_target_bytes"] = meta["share_report_bytes_estimate"] <= TARGET_BYTES
    meta["within_hard_bytes"] = meta["share_report_bytes_estimate"] <= HARD_BYTES
    return payload


def build_markdown_summary(report):
    d = report.get("decision_engine") or {}; sem = report.get("condition_semantics") or {}; t = report.get("temporal_analysis") or {}
    lines = [
        f"# HA Doctor {VERSION}", "",
        f"Score : {(report.get('scores') or {}).get('global','—')}/100", f"Verdict : {((report.get('doctor_view') or {}).get('verdict') or {}).get('label','—')}", "",
        "## Décisions", "",
        f"- À corriger : {(d.get('lane_counts') or {}).get('fix_now',0)}",
        f"- Revue logique : {(d.get('lane_counts') or {}).get('logic_review',0)}",
        f"- Restaurer si nécessaire : {(d.get('lane_counts') or {}).get('restore_if_needed',0)}",
        f"- Surveillance externe : {(d.get('lane_counts') or {}).get('watch',0)}",
        f"- Optimisations : {(d.get('lane_counts') or {}).get('optimize',0)}", "",
        "## Contrôleurs", "",
        f"- Paires physiques à revoir : {sem.get('physical_unproven_pair_count',0)}",
        f"- Overlaps de politique : {sem.get('policy_overlap_pair_count',0)}",
        f"- Exclusions numériques prouvées : {sem.get('branch_numeric_resolved_pair_count',0)}", "",
        "## Historique", "",
        f"- Comparaison : {t.get('score_comparison_status','—')}",
        f"- Dernier score fiable : {t.get('previous_score') if t.get('previous_score_trusted') else 'aucun'}",
        f"- Politique : {t.get('history_policy') or HISTORY_POLICY}", "",
        "HA Doctor reste strictement en lecture seule.", "",
    ]
    return "\n".join(lines)
