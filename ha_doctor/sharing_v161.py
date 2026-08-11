"""HA Doctor 0.16.1 Share V10 compaction hotfix.

Preserves every finding/action identity and the precision evidence required by
support, while removing duplicated representations of the same truth.
"""

import json
from sharing_v160 import build_share_report as _base_build, build_markdown_summary
from contracts_v160 import SHARE_TARGET_BYTES, SHARE_HARD_BYTES


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))


def _pick(obj, keys):
    return {k: obj.get(k) for k in keys if k in obj}


def build_share_report(report):
    payload = _base_build(report)
    if not isinstance(payload, dict):
        return payload

    # Controller scope is already preserved in product_intelligence and each
    # relevant action impact. Do not serialize the full structure a third time.
    condition = payload.get("condition_semantics") or {}
    condition.pop("controller_impact", None)

    # The action array itself is the canonical order. Repeating every ID in a
    # second list adds no support value.
    decision = payload.get("decision_engine") or {}
    order = decision.get("canonical_order") or {}
    decision["canonical_order"] = {
        "model": order.get("model"),
        "preserved_by_action_plan_order": True,
    }

    doctor = payload.get("doctor_view") or {}
    doctor["trust"] = _pick(doctor.get("trust") or {}, (
        "model", "score", "level", "read_only", "single_snapshot_evidence",
        "public_contract_truth", "self_check_status", "final_export_self_validated",
        "temporal_score_comparison_trusted", "temporal_score_comparison_status",
        "current_committed_baseline", "canonical_published_including_current",
    ))

    product = payload.get("product_intelligence") or {}
    impact = product.get("controller_impact") or {}
    product["controller_impact"] = _pick(impact, (
        "model", "scope", "physical_pair_count", "physical_entity_count",
        "impacted_automation_count", "impacted_automations", "target_entities",
        "level", "broad_historical_blast_radius_not_used_for_priority",
    ))

    # Full contract booleans are useful in the primary report, but the support
    # export only needs the aggregate publication truth plus identity models.
    truth = product.get("public_contract_truth") or {}
    product["public_contract_truth"] = {
        "model": truth.get("model"),
        "all_current_contracts_fresh": all(
            bool(v) for k, v in truth.items() if k.endswith("_fresh")
        ),
        "decision_item_identity": bool(truth.get("decision_item_identity")),
        "canonical_order_identity": bool(truth.get("canonical_order_identity")),
        "precision_models_present": bool(truth.get("precision_models_present")),
    }

    # Keep the self-check decision, counts and any failures/warnings, but omit
    # internal proof flags duplicated by export_meta and Doctor Trust.
    sc = payload.get("self_check") or {}
    payload["self_check"] = _pick(sc, (
        "model", "version", "status", "check_count", "pass_count", "warning_count",
        "failure_count", "failures", "warnings", "blocks_publication",
        "final_export_self_validated", "final_export_bytes",
    ))

    meta = payload.get("export_meta") or {}
    meta["v161_duplicate_truth_compaction"] = True
    meta["share_report_bytes_estimate"] = _size(payload)
    meta["within_target_bytes"] = meta["share_report_bytes_estimate"] <= SHARE_TARGET_BYTES
    meta["within_hard_bytes"] = meta["share_report_bytes_estimate"] <= SHARE_HARD_BYTES
    return payload
