"""HA Doctor 0.4 registry-aware diagnostics layer.

Adds integration/device clustering and probable orphan detection through the
official Home Assistant WebSocket registries. The 0.3.2 detection/scoring
engine remains intact; registry insights are preview diagnostics and are not yet
included in the health score.
"""

import scanner as base
import scanner_patch as v030
import scanner_v032 as v032
from registry_analysis import analyze_registry, fetch_registries
from rules import finding

VERSION = "0.4.0"


def _append_orphan_finding(report, registry):
    orphan = registry.get("orphan_analysis") or {}
    count = int(orphan.get("candidate_count", 0) or 0)
    high = int(orphan.get("high_confidence_count", 0) or 0)
    if count <= 0:
        return

    examples = orphan.get("candidates") or []
    item = finding(
        "HD-REG-001",
        "Entités probablement orphelines dans le registre",
        "low",
        "configuration",
        f"{count} entité(s) locale(s) enregistrée(s) semblent ne plus être correctement chargées, dont {high} candidat(s) à confiance élevée.",
        "Vérifier ces entités avant toute suppression. HA Doctor ne modifie jamais le registre et distingue les candidats à confiance élevée des simples indisponibilités locales.",
        examples=examples[:12],
    )
    # Registry findings are intentionally actionable but unscored in 0.4.0.
    item["priority"] = "verify"
    item["priority_label"] = "À vérifier"
    report.setdefault("findings", []).append(item)


def _resync_findings(report):
    findings = report.get("findings") or []
    priority_order = {"action_now": 0, "verify": 1, "optimize": 2, "info": 3}
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda x: (
        priority_order.get(x.get("priority"), 9),
        severity_order.get(x.get("severity"), 9),
        x.get("rule_id", ""),
    ))
    report["findings"] = findings
    report["severity_counts"] = v030._severity_counts(findings)
    report["diagnostic_summary"] = v030._diagnostic_summary(findings)


def scan(include_yaml=True):
    report = v032.scan(include_yaml=include_yaml)
    previous_score = (report.get("scores") or {}).get("global")

    state_errors = []
    states = base._safe_api_get("/core/api/states", state_errors) or []
    registry_payload = fetch_registries()
    registry = analyze_registry(states, registry_payload)
    report["registry_analysis"] = registry

    if registry.get("available"):
        _append_orphan_finding(report, registry)
        _resync_findings(report)

    diagnostics = report.setdefault("diagnostics", {})
    if state_errors:
        diagnostics["registry_state_api_errors"] = state_errors
    if registry.get("errors"):
        diagnostics["registry_api_errors"] = registry.get("errors")

    report["version"] = VERSION
    score_meta = dict(report.get("score_meta") or {})
    score_meta.update({
        "model": "priority_v2-preview",
        "previous_global": previous_score,
        "registry_scoring": False,
        "note": "0.4 ajoute l'analyse des registres, intégrations, appareils et candidats orphelins. Ces nouveaux insights ne modifient pas encore le score Alpha.",
    })
    report["score_meta"] = score_meta
    report.setdefault("privacy", {})["registry_raw_payload_persisted"] = False
    report["privacy"]["registry_auth_token_persisted"] = False
    return report
