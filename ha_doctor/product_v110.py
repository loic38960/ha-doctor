"""HA Doctor 0.11 cross-validated product intelligence.

This layer fixes cross-section drift found by a real 0.10 report. Counts are
now derived from the full finding evidence (not from compact-export-only fields),
and every customer-facing summary is traced back to the same source objects.
"""

import re
from collections import Counter

import product_v100 as base
from contracts_v110 import (
    VERSION, REPORT_SCHEMA, PRODUCT_MODEL, TRIAGE_MODEL, TRUST_MODEL,
    SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
)

_COUNT_RE = re.compile(r"^\s*(\d+)\b")


def _int(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return int(default)


def _finding_map(report):
    return {
        str(item.get("rule_id")): item
        for item in report.get("findings") or []
        if isinstance(item, dict) and item.get("rule_id")
    }


def finding_evidence_count(finding):
    """Return the diagnostic total, not merely the sampled example count."""
    if not isinstance(finding, dict):
        return 0
    candidates = []
    examples = finding.get("examples")
    if isinstance(examples, list):
        candidates.append(len(examples))
    explicit = finding.get("example_count")
    if explicit is not None:
        candidates.append(_int(explicit, 0))
    summary = str(finding.get("summary") or "")
    match = _COUNT_RE.match(summary)
    if match:
        candidates.append(int(match.group(1)))
    return max(candidates or [0])


def _maintenance(report):
    registry = report.get("registry_analysis") or report.get("registry_summary") or {}
    orphan = registry.get("orphan_analysis") or {}
    findings = _finding_map(report)
    local = findings.get("HD-REG-002") or {}
    coverage = findings.get("HD-CFG-005") or {}
    stale_refs = findings.get("HD-CFG-001") or {}
    return {
        "model": "maintenance_intelligence_v2_source_derived",
        "orphan_candidates": _int(orphan.get("candidate_count"), 0),
        "probable_orphans": _int(orphan.get("probable_orphan_count"), 0),
        "high_confidence_orphans": _int(orphan.get("high_confidence_count"), 0),
        "local_unavailable_review": finding_evidence_count(local),
        "missing_reference_count": finding_evidence_count(stale_refs),
        "automation_coverage_summary": coverage.get("summary"),
        "safe_cleanup_candidates": _int(orphan.get("probable_orphan_count"), 0),
        "source_rule_ids": ["HD-REG-002", "HD-CFG-001", "HD-CFG-005"],
        "automatic_cleanup": False,
    }


def _security(report):
    findings = _finding_map(report)
    active = findings.get("HD-SEC-001") or {}
    archive = findings.get("HD-SEC-003") or {}
    active_count = finding_evidence_count(active)
    archive_count = finding_evidence_count(archive)
    posture = "action_required" if active_count else ("review" if archive_count else "good")
    return {
        "model": "security_posture_v2_source_derived",
        "posture": posture,
        "active_secret_hint_count": active_count,
        "archive_secret_hint_count": archive_count,
        "source_rule_ids": ["HD-SEC-001", "HD-SEC-003"],
        "secret_values_in_report": False,
        "read_only_validation": True,
    }


def _single_snapshot_evidence(report):
    perf = report.get("scan_performance") or {}
    privacy = report.get("privacy") or {}
    snapshot = report.get("snapshot_consistency") or report.get("state_snapshot") or {}
    return bool(
        perf.get("single_state_snapshot_preserved")
        or privacy.get("single_ephemeral_state_snapshot")
        or privacy.get("state_snapshot_ephemeral")
        or snapshot.get("single_snapshot")
        or snapshot.get("network_reads") == 1
    )


def _score_trace(report):
    temporal = report.get("temporal_analysis") or {}
    return {
        "model": "score_change_trace_v2",
        "primary_score": _int((report.get("scores") or {}).get("global"), 0),
        "preview_score": _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), 0),
        "previous_score": temporal.get("previous_score"),
        "score_delta": temporal.get("score_delta"),
        "meaningful_previous_generated_at": temporal.get("meaningful_previous_generated_at"),
        "current_generated_at": report.get("generated_at"),
        "history_scope": "primary_score_history",
        "preview_applied_to_primary": False,
    }


def _controller_trace(report):
    sem = report.get("condition_semantics") or {}
    physical = []
    for pair in sem.get("unproven_pairs") or []:
        if not isinstance(pair, dict) or str(pair.get("target_kind") or "") != "actuator":
            continue
        ev = pair.get("v7_evidence") or {}
        physical.append({
            "entity_id": pair.get("entity_id"),
            "automations": list(pair.get("automations") or [])[:2],
            "review_priority": pair.get("review_priority"),
            "reason": ev.get("reason"),
            "evidence_level": ev.get("evidence_level"),
            "opposing_deterministic_intents": ev.get("opposing_deterministic_intents"),
            "numeric_overlap_candidates": list(ev.get("numeric_overlap_candidates") or [])[:4],
            "numeric_disjoint_evidence": list(ev.get("numeric_disjoint_evidence") or [])[:4],
            "templates_executed": bool(ev.get("templates_executed", False)),
        })
    return {
        "model": "controller_review_trace_v1",
        "physical_pair_count": len(physical),
        "numeric_overlap_pair_count": sum(1 for x in physical if x.get("numeric_overlap_candidates")),
        "items": physical[:8],
    }


def _resilience_trace(report):
    recs = report.get("resilience_recommendations") or {}
    items = []
    for item in recs.get("items") or []:
        if not isinstance(item, dict):
            continue
        items.append({
            "entity_id": item.get("entity_id"),
            "tier": item.get("tier"),
            "criticality": _int(item.get("criticality"), 0),
            "unprotected_physical_automation_count": _int(item.get("unprotected_physical_automation_count"), 0),
            "weak_physical_automation_count": _int(item.get("weak_physical_automation_count"), 0),
            "risky_automations": list(item.get("risky_automations") or [])[:10],
        })
    return {
        "model": "resilience_trace_v1",
        "selection_policy": recs.get("selection_policy"),
        "must_fix_count": _int(recs.get("must_fix_count"), 0),
        "hardening_count": _int(recs.get("hardening_count"), 0),
        "items": items,
    }


def _cross_section_truth(report, maintenance, security, controller, resilience):
    findings = _finding_map(report)
    return {
        "model": "cross_section_truth_v1",
        "finding_counts": {
            rule: finding_evidence_count(findings.get(rule) or {})
            for rule in ("HD-SEC-001", "HD-SEC-003", "HD-CFG-001", "HD-REG-002", "HD-AUTO-005")
        },
        "security_active_matches_finding": security.get("active_secret_hint_count") == finding_evidence_count(findings.get("HD-SEC-001") or {}),
        "security_archive_matches_finding": security.get("archive_secret_hint_count") == finding_evidence_count(findings.get("HD-SEC-003") or {}),
        "maintenance_missing_refs_matches_finding": maintenance.get("missing_reference_count") == finding_evidence_count(findings.get("HD-CFG-001") or {}),
        "maintenance_local_review_matches_finding": maintenance.get("local_unavailable_review") == finding_evidence_count(findings.get("HD-REG-002") or {}),
        "physical_controller_evidence_count": controller.get("physical_pair_count", 0),
        "resilience_trace_item_count": len(resilience.get("items") or []),
        "single_snapshot_evidence": _single_snapshot_evidence(report),
    }


def _rebuild_executive(report, product):
    executive = report.setdefault("executive_summary", {})
    sem = report.get("condition_semantics") or {}
    recs = report.get("resilience_recommendations") or {}
    temporal = report.get("temporal_analysis") or {}
    counts = (report.get("action_plan") or {}).get("counts") or {}
    primary = _int((report.get("scores") or {}).get("global"), 0)
    preview = _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), primary)
    security = product.get("security") or {}
    maintenance = product.get("maintenance") or {}
    executive.update({
        "product_model": "product_intelligence_v3_cross_validated",
        "condition_semantics_model": str(sem.get("model") or ""),
        "resilience_recommendation_model": str(recs.get("model") or ""),
        "text": (
            f"Indice de santé V4 {primary}/100 ({executive.get('health_label','—')}). "
            f"Preview V5 {preview}/100, non appliqué au score primaire. "
            f"{counts.get('action_now',0)} correction(s) prioritaire(s), {counts.get('verify',0)} vérification(s), "
            f"{counts.get('optimize',0)} optimisation(s). "
            f"Temporal V3.1 : {temporal.get('persistent_count',0)} persistant(s), {temporal.get('new_count',0)} nouveau(x), "
            f"{temporal.get('resolved_since_previous_count',0)} réellement résolu(s). "
            f"Contrôleurs V7 : {sem.get('physical_unproven_pair_count',0)} paire(s) physique(s) à revoir, "
            f"{sem.get('numeric_overlap_candidate_pair_count',0)} avec overlap numérique littéral. "
            f"Résilience Exposure First : {recs.get('must_fix_count',0)} exposition(s) réelle(s), "
            f"{recs.get('hardening_count',0)} durcissement(s). "
            f"Sécurité : {security.get('active_secret_hint_count',0)} indice(s) actif(s) ; "
            f"maintenance : {maintenance.get('missing_reference_count',0)} référence(s) absente(s)."
        ),
    })


def apply_product_intelligence_v3(report):
    if not isinstance(report, dict):
        return report

    base.apply_product_intelligence_v2(report)
    product = report.setdefault("product_intelligence", {})
    maintenance = _maintenance(report)
    security = _security(report)
    controller = _controller_trace(report)
    resilience = _resilience_trace(report)
    score_trace = _score_trace(report)

    product.update({
        "model": "product_intelligence_v3_cross_validated",
        "maintenance": maintenance,
        "security": security,
        "controller_review_trace": controller,
        "resilience_trace": resilience,
        "score_change_trace": score_trace,
    })
    truth = _cross_section_truth(report, maintenance, security, controller, resilience)
    product["cross_section_truth"] = truth

    doctor = report.setdefault("doctor_view", {})
    doctor["model"] = PRODUCT_MODEL
    trust = dict(doctor.get("trust") or report.get("diagnostic_trust") or {})
    trust["model"] = TRUST_MODEL
    trust["single_snapshot_evidence"] = _single_snapshot_evidence(report)
    trust["cross_section_truth"] = all(
        value for key, value in truth.items()
        if key.endswith("_matches_finding")
    )
    doctor["trust"] = trust
    report["diagnostic_trust"] = trust

    triage = report.setdefault("triage_board", {})
    triage["model"] = TRIAGE_MODEL
    report["share_contract"] = {
        "schema": SHARE_SCHEMA,
        "model": SHARE_MODEL,
        "target_bytes": SHARE_TARGET_BYTES,
        "hard_bytes": SHARE_HARD_BYTES,
        "single_source_of_truth": True,
    }

    _rebuild_executive(report, product)
    report["version"] = VERSION
    schema = report.setdefault("report_schema", {})
    schema["version"] = REPORT_SCHEMA
    capabilities = list(schema.get("capabilities") or [])
    for capability in (
        "finding_source_derived_counts", "security_posture_v2_source_derived",
        "maintenance_intelligence_v2_source_derived", "controller_review_trace_v1",
        "resilience_trace_v1", "score_change_trace_v2", "cross_section_truth_v1",
        "single_snapshot_trust_evidence", "cross_validated_product_layer",
    ):
        if capability not in capabilities:
            capabilities.append(capability)
    schema["capabilities"] = capabilities
    return report
