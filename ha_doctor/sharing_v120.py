"""HA Doctor 0.12 support export with canonical temporal truth preserved."""

import json
import sharing_v110 as base
from contracts_v120 import VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_MODEL, SHARE_TARGET_BYTES, SHARE_HARD_BYTES, HISTORY_CONTRACT

MODEL = SHARE_MODEL
SCHEMA = SHARE_SCHEMA
TARGET_BYTES = SHARE_TARGET_BYTES
HARD_BYTES = SHARE_HARD_BYTES


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _temporal_compact(report):
    temporal = report.get("temporal_analysis") or {}
    integrity = report.get("score_history_integrity") or {}
    trace = (report.get("product_intelligence") or {}).get("score_change_trace") or {}
    return {
        "model": temporal.get("model"),
        "history_contract": temporal.get("history_contract") or HISTORY_CONTRACT,
        "comparison_status": temporal.get("score_comparison_status"),
        "previous_score": temporal.get("previous_score"),
        "previous_score_trusted": temporal.get("previous_score_trusted"),
        "previous_score_source": temporal.get("previous_score_source"),
        "legacy_previous_score_candidate": temporal.get("legacy_previous_score_candidate"),
        "current_primary_score": temporal.get("current_primary_score"),
        "score_delta": temporal.get("score_delta"),
        "meaningful_previous_generated_at": temporal.get("meaningful_previous_generated_at"),
        "false_stability_prevented": temporal.get("false_stability_prevented"),
        "current_snapshot_canonicalized": temporal.get("current_snapshot_canonicalized"),
        "integrity": {key: integrity.get(key) for key in ("model", "contract", "comparison_status", "previous_score_trusted", "false_stability_prevented", "canonical_snapshots_last_10", "legacy_untrusted_snapshots_last_10", "migration") if key in integrity},
        "trace": trace,
    }


def _public_contracts(report):
    product = report.get("product_intelligence") or {}
    return {
        "diagnostic_source": (report.get("diagnostic_summary") or {}).get("source"),
        "action_plan_model": (report.get("action_plan") or {}).get("model"),
        "controller_review_model": (report.get("controller_review_summary") or {}).get("model"),
        "temporal_model": (report.get("temporal_analysis") or {}).get("model"),
        "truth": product.get("public_contract_truth") or {},
    }


def build_share_report(report):
    payload = base.build_share_report(report)
    if not isinstance(payload, dict):
        return payload
    payload["version"] = VERSION
    payload["report_schema"] = {**(payload.get("report_schema") or {}), "version": REPORT_SCHEMA}
    payload["share_schema"] = {"version": SCHEMA, "model": MODEL, "source_report_version": VERSION, "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES}
    payload["temporal_truth"] = _temporal_compact(report)
    payload["public_contracts"] = _public_contracts(report)

    product = payload.setdefault("product_intelligence", {})
    source_product = report.get("product_intelligence") or {}
    product["model"] = source_product.get("model")
    product["score_change_trace"] = source_product.get("score_change_trace") or {}
    product["score_change_explainer"] = source_product.get("score_change_explainer") or {}
    product["public_contract_truth"] = source_product.get("public_contract_truth") or {}
    doctor = payload.setdefault("doctor_view", {})
    doctor["model"] = (report.get("doctor_view") or {}).get("model")
    doctor["trust"] = (report.get("doctor_view") or {}).get("trust") or {}

    meta = payload.setdefault("export_meta", {})
    meta.update({
        "type": MODEL, "source_report_version": VERSION, "target_bytes": TARGET_BYTES, "hard_bytes": HARD_BYTES,
        "contract_source": "contracts_v120", "canonical_temporal_trace_preserved": True,
        "public_contract_truth_preserved": True, "essential_controller_evidence_preserved": True,
        "essential_resilience_trace_preserved": True, "raw_states_included": False,
        "raw_yaml_included": False, "secret_values_included": False,
    })
    if _size(payload) > TARGET_BYTES:
        payload.pop("architecture_summary", None); payload.pop("entity_health_summary", None); payload.pop("non_plan_observations", None)
        product.pop("score_change_explainer", None)
    if _size(payload) > TARGET_BYTES:
        payload.pop("registry_summary", None); payload.pop("entity_lineage_summary", None)
        for finding in payload.get("findings") or []:
            if isinstance(finding, dict):
                for key in list(finding):
                    if key not in {"rule_id", "title", "severity", "domain", "priority", "example_count"}:
                        finding.pop(key, None)
    if _size(payload) > HARD_BYTES:
        payload.pop("system", None); payload.pop("flow_confidence", None); payload.pop("root_cause_summary", None); payload.pop("temporal_analysis", None)
    meta["share_report_bytes_estimate"] = _size(payload)
    meta["within_target_bytes"] = meta["share_report_bytes_estimate"] <= TARGET_BYTES
    meta["within_hard_bytes"] = meta["share_report_bytes_estimate"] <= HARD_BYTES
    meta["detail_level"] = "temporal_truth_evidence_first"
    return payload


def build_markdown_summary(report):
    text = base.build_markdown_summary(report).rstrip()
    temporal = _temporal_compact(report)
    contracts = _public_contracts(report)
    if temporal.get("comparison_status") == "canonical":
        comparison = f"{temporal.get('previous_score')} → {temporal.get('current_primary_score')} (Δ {temporal.get('score_delta'):+d})"
    elif temporal.get("comparison_status") == "legacy_untrusted":
        comparison = "ancien snapshot non canonique : delta volontairement suspendu"
    else:
        comparison = "premier snapshot canonique"
    return "\n".join([text, "", "## Temporal Truth 0.12", "", f"- Comparaison score : {comparison}", f"- Contrat historique : {temporal.get('history_contract') or HISTORY_CONTRACT}", f"- Faux score stable empêché : {'oui' if temporal.get('false_stability_prevented') else 'non'}", f"- Modèle plan : {contracts.get('action_plan_model') or '—'}", f"- Source diagnostic : {contracts.get('diagnostic_source') or '—'}", ""])
