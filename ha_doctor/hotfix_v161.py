"""HA Doctor 0.16.1 publication hotfix.

This module repairs two publication-contract regressions found by the first
real 0.16 field report. It does not alter the technical score or diagnostic
findings:
- every inherited repair playbook is normalized to the current V4 contract;
- resilience pre-control counts distinguish unprotected exposure from weak
  hardening exposure, matching the intended must-fix vs hardening policy.
"""

from contracts_v160 import REPAIR_PLAYBOOK_MODEL

_PRE_CONTROL_PHASES = {
    "pre_control_decision", "mixed_feedback_control", "unresolved_reference_phase",
}


def _normalize_playbooks(report):
    decision = report.get("decision_engine") or {}
    by_id = {}
    for item in decision.get("items") or []:
        if not isinstance(item, dict):
            continue
        playbook = dict(item.get("repair_playbook") or {})
        playbook["model"] = REPAIR_PLAYBOOK_MODEL
        playbook["automatic_fix"] = False
        playbook["read_only"] = True
        item["repair_playbook"] = playbook
        if item.get("id"):
            by_id[str(item.get("id"))] = playbook

    for item in (report.get("action_plan") or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        playbook = by_id.get(str(item.get("id")))
        if playbook is not None:
            item["repair_playbook"] = dict(playbook)

    report.setdefault("diagnostic_engine", {})["v161_playbook_contract_normalized"] = True


def _normalize_resilience_counts(report):
    recs = report.get("resilience_recommendations") or {}
    for rec in recs.get("items") or []:
        if not isinstance(rec, dict):
            continue
        evidence = [x for x in rec.get("phase_evidence") or [] if isinstance(x, dict)]
        unprotected_pre = sum(
            1 for x in evidence
            if x.get("phase") in _PRE_CONTROL_PHASES and str(x.get("protection") or "") == "none"
        )
        weak_pre = sum(
            1 for x in evidence
            if x.get("phase") in _PRE_CONTROL_PHASES and str(x.get("protection") or "") == "weak"
        )
        # In V5 the field name is used by the release gate as the must-fix
        # exposure count. Weak fallbacks remain visible separately as hardening.
        rec["pre_control_risk_count"] = unprotected_pre
        rec["weak_pre_control_risk_count"] = weak_pre
        rec["unprotected_pre_control_risk_count"] = unprotected_pre
        if unprotected_pre > 0:
            rec["tier"] = "must_fix"
            rec["phase_adjustment"] = "unprotected_pre_control_dependency_confirmed"
        elif weak_pre > 0 and rec.get("tier") == "hardening":
            rec["phase_adjustment"] = "weak_pre_control_dependency_hardening"

    recs["must_fix_count"] = sum(1 for x in recs.get("items") or [] if isinstance(x, dict) and x.get("tier") == "must_fix")
    recs["hardening_count"] = sum(1 for x in recs.get("items") or [] if isinstance(x, dict) and x.get("tier") == "hardening")
    report.setdefault("diagnostic_engine", {})["v161_resilience_tier_semantics_normalized"] = True


def apply_hotfix_v161(report):
    if not isinstance(report, dict):
        return report
    _normalize_playbooks(report)
    _normalize_resilience_counts(report)
    report.setdefault("privacy", {}).update({
        "v161_additional_home_assistant_state_reads": 0,
        "v161_automatic_configuration_changes": False,
        "v161_raw_states_persisted": False,
        "v161_raw_yaml_persisted": False,
        "v161_secret_values_persisted": False,
    })
    return report
