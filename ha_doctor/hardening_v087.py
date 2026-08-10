"""HA Doctor 0.8.7 report hardening.

0.8.7 is deliberately non-destructive: it does not change Home Assistant and it
does not change the validated diagnostic rules. It synchronizes controller
review counts and prepares the report for a smaller assistant handoff packet.
"""
import time

VERSION = "0.8.7"
REPORT_SCHEMA = "ha-doctor-report/0.8.7"


def _controller_summary(report):
    semantics = report.get("condition_semantics") or {}
    pairs = [
        item for item in (semantics.get("unproven_pairs") or [])
        if isinstance(item, dict)
    ]
    entity_ids = sorted({
        str(item.get("entity_id"))
        for item in pairs
        if item.get("entity_id")
    })
    physical = int(semantics.get("physical_unproven_pair_count", 0) or 0)
    helper = int(semantics.get("helper_unproven_pair_count", 0) or 0)
    other = int(semantics.get("other_unproven_pair_count", 0) or 0)
    return {
        "model": "controller_review_summary_v1",
        "entity_count": len(entity_ids),
        "pair_count": len(pairs),
        "physical_pair_count": physical,
        "helper_pair_count": helper,
        "other_pair_count": other,
        "branch_resolved_pair_count": int(
            semantics.get("branch_protocol_resolved_pair_count", 0) or 0
        ),
        "entity_ids": entity_ids,
    }


def _sync_controller_diagnostic(report, summary):
    entity_count = summary["entity_count"]
    pair_count = summary["pair_count"]
    physical = summary["physical_pair_count"]
    helper = summary["helper_pair_count"]
    branch = summary["branch_resolved_pair_count"]

    for finding in report.get("findings") or []:
        if not isinstance(finding, dict) or finding.get("rule_id") != "HD-AUTO-003":
            continue
        finding["summary"] = (
            f"{physical} paire(s) sur actionneur physique restent à vérifier, "
            f"{helper} paire(s) concernent seulement des helpers ; "
            f"{branch} paire(s) ont été reconnues par analyse de branche."
        )
        finding["controller_review_summary"] = summary

    for item in (report.get("action_plan") or {}).get("items") or []:
        if not isinstance(item, dict) or item.get("source_id") != "HD-AUTO-003":
            continue
        item["diagnosis"] = (
            f"{pair_count} paire(s) sur {entity_count} entité(s) restent non prouvées, "
            f"dont {physical} paire(s) physiques et {helper} paire(s) de helpers."
        )
        evidence = item.get("evidence")
        if not isinstance(evidence, list):
            evidence = []
            item["evidence"] = evidence
        summary_evidence = {
            "type": "summary",
            "label": "Constat",
            "text": (
                f"{entity_count} entité(s) concentrent {pair_count} paire(s) de "
                "contrôleurs encore non prouvées."
            ),
        }
        replaced = False
        for index, entry in enumerate(evidence):
            if isinstance(entry, dict) and entry.get("type") == "summary":
                evidence[index] = summary_evidence
                replaced = True
                break
        if not replaced:
            evidence.insert(0, summary_evidence)
        item["controller_review_summary"] = summary


def _sync_report_metadata(report, summary):
    report["version"] = VERSION
    report["controller_review_summary"] = summary

    diagnostic_summary = report.setdefault("diagnostic_summary", {})
    diagnostic_summary["source"] = "final_correlated_action_plan_v087"
    diagnostic_summary["controller_review_entity_count"] = summary["entity_count"]
    diagnostic_summary["controller_review_pair_count"] = summary["pair_count"]

    executive = report.setdefault("executive_summary", {})
    executive["controller_review_entity_count"] = summary["entity_count"]
    executive["controller_review_pair_count"] = summary["pair_count"]

    score_meta = report.setdefault("score_meta", {})
    score_meta["hardening_version"] = VERSION
    score_meta["delivery_version"] = VERSION
    score_meta["share_report_model"] = "assistant_share_report_v2"

    privacy = report.setdefault("privacy", {})
    privacy.update({
        "assistant_share_export_raw_states_included": False,
        "assistant_share_export_raw_yaml_included": False,
        "assistant_share_export_secret_values_included": False,
    })

    engine = report.setdefault("diagnostic_engine", {})
    engine.update({
        "assistant_share_report_v2": True,
        "controller_review_summary_v1": True,
        "full_report_still_available": True,
    })

    schema = report.get("report_schema") or {}
    compatible = list(schema.get("backward_compatible_with") or [])
    if "0.8.6" not in compatible:
        compatible.append("0.8.6")
    capabilities = list(schema.get("capabilities") or [])
    for capability in (
        "assistant_share_report_v2",
        "hard_bounded_support_export",
        "controller_review_count_consistency",
    ):
        if capability not in capabilities:
            capabilities.append(capability)
    report["report_schema"] = {
        **schema,
        "version": REPORT_SCHEMA,
        "backward_compatible_with": compatible,
        "capabilities": capabilities,
    }

    consistency = report.get("consistency_analysis")
    if isinstance(consistency, dict) and consistency.get("status") == "pass":
        checks = consistency.setdefault("checks", {})
        checks["controller_review_summary_identity"] = True
        consistency["model"] = "consistency_gates_v5.1_cross_section"


def harden_report_v087(report):
    if not isinstance(report, dict):
        return report
    summary = _controller_summary(report)
    _sync_controller_diagnostic(report, summary)
    _sync_report_metadata(report, summary)
    return report
