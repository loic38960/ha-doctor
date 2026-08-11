"""HA Doctor 0.16 controller evidence precision.

V11 preserves V10 event-window semantics and adds an exact impact scope for the
controller pairs that remain unresolved. The historical shared-actuator finding
can have a broad architecture blast radius; this layer explicitly separates
that broad context from the two automations and physical targets that still
need human review.
"""

from semantics_v150 import refine_condition_semantics_v10
from contracts_v160 import CONDITION_MODEL, CONTROLLER_IMPACT_MODEL


def _pair_signature(pair):
    return {
        "entity_id": str(pair.get("entity_id") or ""),
        "automations": sorted(str(x) for x in pair.get("automations") or [] if x),
        "target_kind": str(pair.get("target_kind") or "other"),
        "review_priority": str(pair.get("review_priority") or "low"),
    }


def build_controller_impact_v2(semantics):
    pairs = [x for x in semantics.get("unproven_pairs") or [] if isinstance(x, dict)]
    physical = [x for x in pairs if str(x.get("target_kind") or "") == "actuator"]
    helpers = [x for x in pairs if str(x.get("target_kind") or "") == "helper"]
    physical_automations = sorted({str(a) for pair in physical for a in pair.get("automations") or [] if a})
    physical_entities = sorted({str(pair.get("entity_id")) for pair in physical if pair.get("entity_id")})
    helper_automations = sorted({str(a) for pair in helpers for a in pair.get("automations") or [] if a})
    exact_weight = round(len(physical) * 2.0 + len(physical_entities) * 1.5 + len(physical_automations) * 0.75, 2)
    if len(physical) >= 3 or len(physical_automations) >= 5:
        level = "high"
    elif physical:
        level = "medium"
    else:
        level = "none"
    return {
        "model": CONTROLLER_IMPACT_MODEL,
        "scope": "unresolved_physical_pairs_only",
        "physical_pair_count": len(physical),
        "physical_entity_count": len(physical_entities),
        "impacted_automation_count": len(physical_automations),
        "impacted_automations": physical_automations,
        "target_entities": physical_entities,
        "helper_pair_count": len(helpers),
        "helper_automation_count": len(helper_automations),
        "level": level,
        "weighted_impact_score": exact_weight,
        "broad_historical_blast_radius_not_used_for_priority": True,
        "physical_pairs": [_pair_signature(x) for x in physical[:10]],
    }


def _sync_controller_finding(report, impact):
    for finding in report.get("findings") or []:
        if not isinstance(finding, dict) or finding.get("rule_id") != "HD-AUTO-003":
            continue
        finding["precision"] = {
            "scope": impact["scope"],
            "physical_pair_count": impact["physical_pair_count"],
            "impacted_automation_count": impact["impacted_automation_count"],
            "target_entities": impact["target_entities"],
        }
        finding["summary_precision"] = (
            f"{impact['physical_pair_count']} paire(s) physique(s) restent réellement à revoir, "
            f"impliquant {impact['impacted_automation_count']} automatisation(s) distincte(s)."
        )
        break


def refine_condition_semantics_v11(report):
    result = refine_condition_semantics_v10(report)
    result = dict(result)
    result["model"] = CONDITION_MODEL
    impact = build_controller_impact_v2(result)
    result["controller_impact"] = impact
    result["exact_unresolved_physical_automation_count"] = impact["impacted_automation_count"]
    result["exact_unresolved_physical_entity_count"] = impact["physical_entity_count"]
    for pair in result.get("unproven_pairs") or []:
        if not isinstance(pair, dict):
            continue
        pair["impact_scope"] = "physical_review" if pair.get("target_kind") == "actuator" else "helper_review"
        pair["counts_toward_physical_blast_radius"] = pair.get("target_kind") == "actuator"
    report["condition_semantics"] = result
    report["controller_impact"] = impact
    _sync_controller_finding(report, impact)
    return result
