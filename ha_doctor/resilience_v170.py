"""HA Doctor 0.17 actionable resilience evidence.

Builds on phase-aware V5 and turns each dependency finding into a concrete guard
strategy without editing Home Assistant or inventing behavior. The strategy is
advisory and keeps must-fix vs hardening distinct.
"""

from resilience_v160 import refine_resilience_v5
from contracts_v170 import RESILIENCE_MODEL, RESILIENCE_RECOMMENDATION_MODEL


def _guard_strategy(row):
    entity_id = str(row.get("entity_id") or "")
    tier = str(row.get("tier") or "hardening")
    risky = list(row.get("risky_automations") or [])
    if tier == "must_fix":
        return {
            "strategy": "explicit_availability_gate_before_physical_control",
            "entity_id": entity_id,
            "recommended_conditions": ["state not unavailable", "state not unknown"],
            "safe_failure_policy": "do_not_issue_the_dependent_physical_command_until_input_is_valid",
            "affected_automations": risky[:12],
            "automatic_change": False,
        }
    return {
        "strategy": "strengthen_weak_fallback_with_explicit_validity_signal",
        "entity_id": entity_id,
        "recommended_conditions": ["distinguish_missing_measurement_from_numeric_zero"],
        "safe_failure_policy": "keep_existing_behavior_until_manual_intent_is_confirmed",
        "affected_automations": risky[:12],
        "automatic_change": False,
    }


def refine_resilience_v6(report):
    refine_resilience_v5(report)
    base = report.get("resilience_recommendations") or {}
    items = []
    for raw in base.get("items") or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["guard_strategy"] = _guard_strategy(row)
        row["resolution_status"] = "logic_review_required" if row.get("tier") == "must_fix" else "optimization"
        row["static_phase_proof"] = {
            "pre_control_risk_count": int(row.get("pre_control_risk_count", 0) or 0),
            "post_action_confirmation_count": int(row.get("post_action_confirmation_count", 0) or 0),
            "trigger_dependency_count": int(row.get("trigger_dependency_count", 0) or 0),
            "phase_adjustment": row.get("phase_adjustment"),
        }
        items.append(row)
    result = {
        **base,
        "model": RESILIENCE_RECOMMENDATION_MODEL,
        "analysis_model": RESILIENCE_MODEL,
        "items": items,
        "must_fix_count": sum(1 for x in items if x.get("tier") == "must_fix"),
        "hardening_count": sum(1 for x in items if x.get("tier") == "hardening"),
        "guard_strategy_count": len(items),
        "automatic_fix": False,
        "read_only": True,
    }
    report["resilience_recommendations"] = result
    precision = dict(report.get("resilience_precision") or {})
    precision["model"] = RESILIENCE_MODEL
    precision["guard_strategy_count"] = len(items)
    precision["must_fix_entities"] = [x.get("entity_id") for x in items if x.get("tier") == "must_fix"]
    report["resilience_precision"] = precision
    return result
