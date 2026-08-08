"""HA Doctor 0.5 explanatory layer.

Builds on 0.4.1 registry calibration and adds a deterministic local diagnostic
engine: executive summary, root-cause incidents, confidence, evidence and an
ordered action plan. The score remains unchanged in 0.5.0 while this layer is
validated on real installations.
"""

import scanner_v041 as v041
from diagnostic_explain import enrich_report

VERSION = "0.5.0"


def scan(include_yaml=True):
    report = v041.scan(include_yaml=include_yaml)
    previous_score = (report.get("scores") or {}).get("global")
    report = enrich_report(report)
    report["version"] = VERSION

    score_meta = dict(report.get("score_meta") or {})
    score_meta.update({
        "model": "priority_v3-explain-preview",
        "previous_global": previous_score,
        "registry_scoring": False,
        "explanatory_scoring": False,
        "note": (
            "0.5 ajoute un moteur local d'explication, de corrélation et de plan d'action. "
            "Les nouvelles explications et causes racines ne modifient pas encore l'indice de santé Alpha."
        ),
    })
    report["score_meta"] = score_meta
    return report
