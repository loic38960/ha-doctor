"""HA Doctor 0.12 product layer: temporal truth and fresh public contracts."""

import product_v110 as base
from contracts_v120 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    PRODUCT_MODEL, TRIAGE_MODEL, TRUST_MODEL, TEMPORAL_MODEL, HISTORY_CONTRACT,
    SCORE_TRACE_MODEL, CONTROLLER_REVIEW_MODEL, ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE,
)


def _int(value, default=0):
    try:
        return int(value if value is not None else default)
    except Exception:
        return int(default)


def _score_trace(report):
    temporal = report.get("temporal_analysis") or {}
    primary = _int((report.get("scores") or {}).get("global"), 0)
    trusted = bool(temporal.get("previous_score_trusted"))
    return {
        "model": SCORE_TRACE_MODEL,
        "primary_score": primary,
        "preview_score": _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), primary),
        "previous_score": temporal.get("previous_score") if trusted else None,
        "score_delta": temporal.get("score_delta") if trusted else None,
        "previous_score_trusted": trusted,
        "previous_score_source": temporal.get("previous_score_source"),
        "legacy_previous_score_candidate": temporal.get("legacy_previous_score_candidate"),
        "comparison_status": temporal.get("score_comparison_status"),
        "meaningful_previous_generated_at": temporal.get("meaningful_previous_generated_at"),
        "current_generated_at": report.get("generated_at"),
        "history_contract": HISTORY_CONTRACT,
        "history_scope": "canonical_final_published_primary_score",
        "preview_applied_to_primary": False,
        "false_stability_prevented": bool(temporal.get("false_stability_prevented")),
    }


def _score_explainer(report, trace):
    status = trace.get("comparison_status")
    current = trace.get("primary_score")
    previous = trace.get("previous_score")
    delta = trace.get("score_delta")
    if status == "canonical" and previous is not None and delta is not None:
        if delta == 0:
            reason = f"Score primaire stable à {current}/100 depuis le dernier snapshot canonique publié."
        else:
            reason = f"Score primaire {delta:+d} point(s) depuis le dernier snapshot canonique publié ({previous} → {current})."
    elif status == "legacy_untrusted":
        candidate = trace.get("legacy_previous_score_candidate")
        suffix = f" (ancienne valeur intermédiaire observée : {candidate})" if candidate is not None else ""
        reason = "Comparaison suspendue : le snapshot précédent est antérieur au contrat 0.12 et son score publié exact n'est pas prouvé" + suffix + "."
    else:
        reason = "Premier snapshot canonique : aucun score publié précédent fiable n'est encore disponible pour calculer un delta."
    return {
        "model": "score_change_explainer_v2_canonical_history",
        "primary_score": current,
        "preview_score": trace.get("preview_score"),
        "previous_score": previous,
        "score_delta": delta,
        "previous_score_trusted": bool(trace.get("previous_score_trusted")),
        "comparison_status": status,
        "reason": reason,
        "v5_preview_not_applied_to_primary": True,
    }


def _refresh_controller_summary(report):
    sem = report.get("condition_semantics") or {}
    trace = (report.get("product_intelligence") or {}).get("controller_review_trace") or {}
    unproven = [x for x in sem.get("unproven_pairs") or [] if isinstance(x, dict)]
    physical = [x for x in unproven if str(x.get("target_kind") or "") == "actuator"]
    helpers = [x for x in unproven if str(x.get("target_kind") or "") == "helper"]
    other = [x for x in unproven if str(x.get("target_kind") or "") not in {"actuator", "helper"}]
    summary = report.setdefault("controller_review_summary", {})
    summary.update({
        "model": CONTROLLER_REVIEW_MODEL,
        "entity_count": len({str(x.get('entity_id')) for x in unproven if x.get('entity_id')}),
        "pair_count": len(unproven),
        "physical_pair_count": len(physical),
        "helper_pair_count": len(helpers),
        "other_pair_count": len(other),
        "numeric_overlap_pair_count": _int(trace.get("numeric_overlap_pair_count"), 0),
        "evidence_item_count": len(trace.get("items") or []),
        "semantic_model": sem.get("model"),
        "remaining_physical_entities": sorted({str(x.get("entity_id")) for x in physical if x.get("entity_id")}),
    })
    for item in (report.get("action_plan") or {}).get("items") or []:
        if isinstance(item, dict) and item.get("id") == "DX-HD-AUTO-003":
            item["controller_review_summary"] = {key: summary.get(key) for key in ("model", "entity_count", "pair_count", "physical_pair_count", "helper_pair_count", "numeric_overlap_pair_count", "evidence_item_count")}
    diagnostic = report.setdefault("diagnostic_summary", {})
    diagnostic["controller_review_entity_count"] = summary["entity_count"]
    diagnostic["controller_review_pair_count"] = summary["pair_count"]
    return summary


def _refresh_quality_detail(report):
    quality = report.get("quality_gates") or {}
    sem = report.get("condition_semantics") or {}
    trace = (report.get("product_intelligence") or {}).get("controller_review_trace") or {}
    for gate in quality.get("gates") or []:
        if isinstance(gate, dict) and gate.get("key") == "condition_semantics":
            gate["detail"] = (
                f"{sem.get('resolved_pair_count',0)} résolue(s) · "
                f"{trace.get('numeric_overlap_pair_count',0)} overlap(s) littéral(aux) · "
                f"{sem.get('physical_unproven_pair_count',0)} physique(s) à revoir · "
                f"{sem.get('helper_unproven_pair_count',0)} helper(s)"
            )
    non_pass = [{k: gate.get(k) for k in ("key", "label", "status", "detail")} for gate in quality.get("gates") or [] if isinstance(gate, dict) and gate.get("status") != "pass"]
    if "non_pass_gates" in quality or non_pass:
        quality["non_pass_gates"] = non_pass


def _public_contract_truth(report):
    diagnostic = report.get("diagnostic_summary") or {}
    action = report.get("action_plan") or {}
    controller = report.get("controller_review_summary") or {}
    temporal = report.get("temporal_analysis") or {}
    return {
        "model": "public_contract_truth_v1",
        "diagnostic_source": diagnostic.get("source"),
        "action_plan_model": action.get("model"),
        "controller_review_model": controller.get("model"),
        "temporal_model": temporal.get("model"),
        "diagnostic_source_fresh": diagnostic.get("source") == ACTION_PLAN_SOURCE,
        "action_plan_model_fresh": action.get("model") == ACTION_PLAN_MODEL,
        "controller_review_model_fresh": controller.get("model") == CONTROLLER_REVIEW_MODEL,
        "temporal_model_fresh": temporal.get("model") == TEMPORAL_MODEL,
        "quality_condition_detail_version_neutral": all(
            "V6" not in str(gate.get("detail") or "")
            for gate in (report.get("quality_gates") or {}).get("gates") or []
            if isinstance(gate, dict) and gate.get("key") == "condition_semantics"
        ),
    }


def _rebuild_executive(report, trace):
    executive = report.setdefault("executive_summary", {})
    sem = report.get("condition_semantics") or {}
    recs = report.get("resilience_recommendations") or {}
    product = report.get("product_intelligence") or {}
    security = product.get("security") or {}
    maintenance = product.get("maintenance") or {}
    temporal = report.get("temporal_analysis") or {}
    counts = (report.get("action_plan") or {}).get("counts") or {}
    primary = _int((report.get("scores") or {}).get("global"), 0)
    preview = _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), primary)
    if trace.get("comparison_status") == "canonical" and trace.get("score_delta") is not None:
        change = f"score Δ {int(trace.get('score_delta')):+d}."
    elif trace.get("comparison_status") == "legacy_untrusted":
        change = "delta score suspendu : historique pré-0.12 non canonique."
    else:
        change = "premier snapshot de score canonique."
    executive.update({
        "product_model": "product_intelligence_v4_temporal_truth",
        "temporal_model": TEMPORAL_MODEL,
        "score_history_contract": HISTORY_CONTRACT,
        "score_comparison_status": trace.get("comparison_status"),
        "previous_score_trusted": bool(trace.get("previous_score_trusted")),
        "text": (
            f"Indice de santé V4 {primary}/100 ({executive.get('health_label','—')}). "
            f"Preview V5 {preview}/100, non appliqué au score primaire. {change} "
            f"{counts.get('action_now',0)} correction(s) prioritaire(s), {counts.get('verify',0)} vérification(s), {counts.get('optimize',0)} optimisation(s). "
            f"Temporal V4 : {temporal.get('persistent_count',0)} persistant(s), {temporal.get('new_count',0)} nouveau(x), {temporal.get('resolved_since_previous_count',0)} réellement résolu(s). "
            f"Contrôleurs V7 : {sem.get('physical_unproven_pair_count',0)} paire(s) physique(s) à revoir, {sem.get('numeric_overlap_candidate_pair_count',0)} avec overlap numérique littéral. "
            f"Résilience Exposure First : {recs.get('must_fix_count',0)} exposition(s) réelle(s), {recs.get('hardening_count',0)} durcissement(s). "
            f"Sécurité : {security.get('active_secret_hint_count',0)} indice(s) actif(s) ; maintenance : {maintenance.get('missing_reference_count',0)} référence(s) absente(s)."
        ),
    })


def apply_product_intelligence_v4(report):
    if not isinstance(report, dict):
        return report
    base.apply_product_intelligence_v3(report)
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report.setdefault("action_plan", {})["model"] = ACTION_PLAN_MODEL
    report.setdefault("diagnostic_summary", {})["source"] = ACTION_PLAN_SOURCE
    report["diagnostic_summary"]["plan_id_count"] = len((report.get("action_plan") or {}).get("items") or [])

    product = report.setdefault("product_intelligence", {})
    product["model"] = "product_intelligence_v4_temporal_truth"
    trace = _score_trace(report)
    product["score_change_trace"] = trace
    product["score_change_explainer"] = _score_explainer(report, trace)

    doctor = report.setdefault("doctor_view", {})
    doctor["model"] = PRODUCT_MODEL
    trust = dict(doctor.get("trust") or report.get("diagnostic_trust") or {})
    trust.update({"model": TRUST_MODEL, "temporal_score_comparison_trusted": bool(trace.get("previous_score_trusted")), "temporal_score_comparison_status": trace.get("comparison_status"), "canonical_history_contract": HISTORY_CONTRACT})
    doctor["trust"] = trust
    report["diagnostic_trust"] = trust
    report.setdefault("triage_board", {})["model"] = TRIAGE_MODEL

    _refresh_controller_summary(report)
    _refresh_quality_detail(report)
    truth = _public_contract_truth(report)
    product["public_contract_truth"] = truth
    product.setdefault("cross_section_truth", {})["public_contracts_fresh"] = all(bool(value) for key, value in truth.items() if key.endswith("_fresh")) and bool(truth.get("quality_condition_detail_version_neutral"))

    report["share_contract"] = {"schema": SHARE_SCHEMA, "model": SHARE_MODEL, "target_bytes": SHARE_TARGET_BYTES, "hard_bytes": SHARE_HARD_BYTES, "single_source_of_truth": True}
    _rebuild_executive(report, trace)

    schema = report.setdefault("report_schema", {})
    capabilities = list(schema.get("capabilities") or [])
    for capability in (
        "temporal_v4_canonical_published_score", "legacy_score_no_guessing", "false_stability_prevention",
        "score_change_trace_v3_canonical_history", "public_contract_truth_v1", "controller_review_summary_v3_evidence",
        "action_plan_model_v4", "version_neutral_quality_detail", "canonical_history_contract_v1", "temporal_truth_product_layer",
    ):
        if capability not in capabilities:
            capabilities.append(capability)
    schema["capabilities"] = capabilities
    return report
