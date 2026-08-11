"""Current controller evidence trace for HA Doctor 0.14."""

from contracts_v140 import CONDITION_MODEL


def build_controller_trace_v9(report):
    sem = report.get("condition_semantics") or {}
    items = []
    for pair in sem.get("unproven_pairs") or []:
        if not isinstance(pair, dict) or str(pair.get("target_kind") or "") != "actuator":
            continue
        analysis = pair.get("v9_policy_analysis") or {}
        conflicts = []
        for raw in analysis.get("conflicts") or []:
            if not isinstance(raw, dict):
                continue
            conflicts.append({
                "intent_a": raw.get("intent_a"),
                "intent_b": raw.get("intent_b"),
                "trigger_a": raw.get("trigger_a"),
                "trigger_b": raw.get("trigger_b"),
                "overlap_evidence": list(raw.get("overlap_evidence") or [])[:4],
            })
        items.append({
            "entity_id": pair.get("entity_id"),
            "automations": list(pair.get("automations") or [])[:2],
            "review_priority": pair.get("review_priority"),
            "evidence_level": pair.get("evidence_level") or ("probable" if analysis.get("status") == "policy_overlap" else "hypothesis"),
            "policy_status": analysis.get("status") or "review",
            "conflict_path_pair_count": analysis.get("conflict_path_pair_count", 0),
            "numerically_disjoint_path_pair_count": analysis.get("numerically_disjoint_path_pair_count", 0),
            "conflicts": conflicts[:6],
            "simultaneous_execution_proven": bool(analysis.get("simultaneous_execution_proven", False)),
            "templates_executed": False,
        })
    trace = {
        "model": "controller_review_trace_v2_policy_overlap",
        "condition_model": sem.get("model") or CONDITION_MODEL,
        "physical_pair_count": len(items),
        "policy_overlap_pair_count": sum(1 for x in items if x.get("policy_status") == "policy_overlap"),
        "branch_numeric_resolved_pair_count": sem.get("branch_numeric_resolved_pair_count", 0),
        "items": items[:10],
        "templates_executed": False,
    }
    report.setdefault("product_intelligence", {})["controller_review_trace"] = trace
    report["controller_evidence"] = trace
    return trace
