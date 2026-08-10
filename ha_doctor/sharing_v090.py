"""HA Doctor 0.9 compact support and human-readable exports."""
import json

import sharing_v088 as base

VERSION = "0.9.0"
MODEL = "assistant_share_report_v3"
SCHEMA = "ha-doctor-share/3"
TARGET_BYTES = 28_000
HARD_BYTES = 32_000


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _text(value, limit=260):
    if value is None:
        return None
    value = str(value)
    return value if len(value) <= limit else value[:limit] + "…"


def _doctor_compact(report):
    doctor = report.get("doctor_view") or {}
    trust = doctor.get("trust") or report.get("diagnostic_trust") or {}
    changes = doctor.get("change_digest") or report.get("change_digest") or {}
    actions = []
    for item in doctor.get("next_best_actions") or []:
        if not isinstance(item, dict):
            continue
        actions.append({
            key: item.get(key)
            for key in (
                "id", "title", "lane", "risk_score", "confidence_tier",
                "repair_mode", "effort", "estimated_score_gain",
                "dependency_impact", "impacted_automation_count",
            )
            if key in item
        })
    return {
        "model": doctor.get("model"),
        "verdict": doctor.get("verdict"),
        "technical_health_score": doctor.get("technical_health_score"),
        "score_v5_preview": doctor.get("score_v5_preview"),
        "projected_after_top_3": doctor.get("projected_after_top_3"),
        "triage_counts": doctor.get("triage_counts") or {},
        "next_best_actions": actions[:7],
        "trust": {
            key: trust.get(key)
            for key in (
                "model", "score", "level", "quality_overall", "consistency_status",
                "flow_status", "lineage_parse_error_count", "unresolved_dynamic_target_count",
                "read_only", "external_ai_used",
            )
            if key in trust
        },
        "noise_reduction": doctor.get("noise_reduction") or {},
        "change_digest": changes,
        "automatic_fix": False,
        "read_only": True,
    }


def _self_check_compact(report):
    source = report.get("self_check") or {}
    return {
        key: source.get(key)
        for key in (
            "model", "status", "check_count", "pass_count", "warning_count",
            "failure_count", "failures", "warnings", "blocks_publication",
        )
        if key in source
    }


def _strip_optional(payload, level):
    if level >= 1:
        payload.pop("architecture_summary", None)
        payload.pop("entity_health_summary", None)
        payload.pop("non_plan_observations", None)
    if level >= 2:
        payload.pop("score_v5_preview", None)
        registry = payload.get("registry_summary") or {}
        for key in ("actionable_integrations", "actionable_devices"):
            for item in registry.get(key) or []:
                if isinstance(item, dict):
                    item.pop("examples", None)
        for finding in payload.get("findings") or []:
            if isinstance(finding, dict):
                finding.pop("examples", None)
                finding.pop("recommendation", None)
                if finding.get("summary"):
                    finding["summary"] = _text(finding["summary"], 180)
    if level >= 3:
        payload.pop("registry_summary", None)
        payload.pop("architecture_summary", None)
        payload.pop("entity_health_summary", None)
        payload.pop("non_plan_observations", None)
        for finding in payload.get("findings") or []:
            if isinstance(finding, dict):
                finding.pop("summary", None)
                finding.pop("priority_label", None)
        for item in (payload.get("action_plan") or {}).get("items") or []:
            if isinstance(item, dict):
                item.pop("first_check", None)
                item.pop("temporal", None)
                impact = item.get("dependency_impact") or {}
                if isinstance(impact, dict):
                    for key in list(impact):
                        if key not in {"level", "impacted_automation_count", "weighted_impact_score"}:
                            impact.pop(key, None)


def build_share_report(report):
    if not isinstance(report, dict):
        return None
    payload = base.build_share_report(report)
    if not isinstance(payload, dict):
        return payload

    payload["version"] = VERSION
    payload["doctor_view"] = _doctor_compact(report)
    payload["self_check"] = _self_check_compact(report)
    payload["share_schema"] = {
        "version": SCHEMA,
        "model": MODEL,
        "source_report_version": VERSION,
        "target_bytes": TARGET_BYTES,
        "hard_bytes": HARD_BYTES,
    }
    payload.setdefault("report_schema", {})["version"] = "ha-doctor-report/0.9"

    meta = payload.setdefault("export_meta", {})
    meta.update({
        "type": MODEL,
        "source_report_version": VERSION,
        "intended_for": "assistant_or_support_analysis",
        "raw_states_included": False,
        "raw_yaml_included": False,
        "secret_values_included": False,
        "full_dependency_graph_included": False,
        "all_action_identities_preserved": True,
        "all_finding_identities_preserved": True,
    })

    level = 0
    while _size(payload) > TARGET_BYTES and level < 3:
        level += 1
        _strip_optional(payload, level)
    meta["detail_level"] = ["standard", "compact", "minimal", "identity_first"][level]
    meta["share_report_bytes_estimate"] = _size(payload)

    if _size(payload) > HARD_BYTES:
        # Last-resort identity-first packet: keep every diagnostic/action identity
        # and the product triage, but remove descriptive repetition.
        for key in (
            "system", "inventory_summary", "registry_summary", "flow_confidence",
            "architecture_summary", "entity_lineage_summary", "resilience",
            "root_cause_summary", "temporal_analysis", "score_v5_preview",
            "non_plan_observations", "entity_health_summary",
        ):
            payload.pop(key, None)
        for finding in payload.get("findings") or []:
            if isinstance(finding, dict):
                for key in list(finding):
                    if key not in {"rule_id", "title", "severity", "domain", "priority"}:
                        finding.pop(key, None)
        for item in (payload.get("action_plan") or {}).get("items") or []:
            if isinstance(item, dict):
                for key in list(item):
                    if key not in {
                        "id", "title", "priority", "severity", "domain", "confidence",
                        "confidence_score", "source_type", "source_id",
                    }:
                        item.pop(key, None)
        meta["detail_level"] = "hard_bounded_identity_first"
        meta["secondary_sections_omitted"] = True
        meta["share_report_bytes_estimate"] = _size(payload)

    return payload


def build_markdown_summary(report):
    doctor = report.get("doctor_view") or {}
    verdict = doctor.get("verdict") or {}
    trust = doctor.get("trust") or report.get("diagnostic_trust") or {}
    changes = doctor.get("change_digest") or report.get("change_digest") or {}
    score = int((report.get("scores") or {}).get("global", 0) or 0)
    preview = doctor.get("score_v5_preview", score)
    projected = doctor.get("projected_after_top_3", score)
    triage = doctor.get("triage_counts") or {}
    self_check = report.get("self_check") or {}

    lines = [
        "# Rapport HA Doctor",
        "",
        f"**Version :** {VERSION}",
        f"**Date :** {report.get('generated_at') or '—'}",
        f"**Verdict :** {verdict.get('label') or verdict.get('code') or '—'}",
        f"**Score technique V4 :** {score}/100",
        f"**Preview V5 :** {preview}/100",
        f"**Projection après les 3 premières corrections :** {projected}/100",
        f"**Confiance du diagnostic :** {trust.get('score','—')}/100 ({trust.get('level','—')})",
        "",
        "## Priorités",
        "",
        f"- À corriger maintenant : {triage.get('fix_now',0)}",
        f"- À investiguer : {triage.get('investigate',0)}",
        f"- À revoir : {triage.get('review',0)}",
        f"- Optimisations : {triage.get('optimize',0)}",
        "",
        "## Les prochaines actions",
        "",
    ]

    actions = doctor.get("next_best_actions") or []
    if not actions:
        lines.append("Aucune action prioritaire dans le plan courant.")
    for index, item in enumerate(actions[:7], start=1):
        gain = float(item.get("estimated_score_gain", 0) or 0)
        suffix = f" · gain estimé +{gain:.2f}" if gain > 0 else ""
        lines.extend([
            f"### {index}. {item.get('title') or item.get('id') or 'Action'}",
            f"- Priorité : {item.get('lane','—')} · risque {item.get('risk_score','—')}/100 · confiance {item.get('confidence_tier','—')}{suffix}",
            f"- Type : {item.get('repair_mode','—')} · effort : {item.get('effort','—')}",
        ])
        first = item.get("first_check") or {}
        if first:
            lines.append(f"- Premier contrôle : {first.get('title') or ''} — {first.get('detail') or ''}")
        lines.append("")

    lines.extend([
        "## Évolution",
        "",
        f"- Nouveaux : {changes.get('new',0)}",
        f"- Persistants : {changes.get('persistent',0)}",
        f"- Résolus : {changes.get('resolved',0)}",
        f"- Déclassés : {changes.get('deescalated',0)}",
        "",
        "## Auto-contrôle HA Doctor",
        "",
        f"- Statut : {self_check.get('status','—')}",
        f"- Contrôles réussis : {self_check.get('pass_count',0)}/{self_check.get('check_count',0)}",
        f"- Avertissements : {self_check.get('warning_count',0)}",
        f"- Échecs : {self_check.get('failure_count',0)}",
        "",
        "## Confidentialité",
        "",
        "HA Doctor fonctionne en lecture seule. Ce résumé ne contient aucun état brut, YAML brut ni valeur de secret.",
        "",
    ])
    return "\n".join(lines)
