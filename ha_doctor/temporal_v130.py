"""HA Doctor 0.13 canonical history stamping.

The score contract remains published_primary_score_v1. This wrapper only makes
the final snapshot metadata truthful for the 0.13 report and decision models.
"""

from temporal_v060 import load_history, save_history
import temporal_v120 as base
from contracts_v130 import (
    VERSION, REPORT_SCHEMA, HISTORY_CONTRACT, TEMPORAL_MODEL,
    ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE, DECISION_MODEL, CONDITION_MODEL,
)


def sync_decision_history(report, history_path=None, publication_complete=False):
    if not isinstance(report, dict):
        return {"synced": False, "reason": "report_not_object"}
    history_path = history_path or base._history_path_default()
    history = load_history(history_path)
    generated_at = str(report.get("generated_at") or "")
    if not history or str(history[-1].get("generated_at") or "") != generated_at:
        return {"synced": False, "reason": "current_snapshot_not_found"}
    score = base._int((report.get("scores") or {}).get("global"), 0)
    preview = base._int((report.get("score_v5_preview") or {}).get("v5_preview_score"), score)
    snap = dict(history[-1])
    snap.update({
        "health_score_v3": score,
        "final_primary_score": score,
        "final_preview_score": preview,
        "score_contract": HISTORY_CONTRACT,
        "report_version": VERSION,
        "report_schema": REPORT_SCHEMA,
        "temporal_model": TEMPORAL_MODEL,
        "action_plan_model": (report.get("action_plan") or {}).get("model") or ACTION_PLAN_MODEL,
        "diagnostic_source": (report.get("diagnostic_summary") or {}).get("source") or ACTION_PLAN_SOURCE,
        "decision_model": (report.get("decision_engine") or {}).get("model") or DECISION_MODEL,
        "condition_model": (report.get("condition_semantics") or {}).get("model") or CONDITION_MODEL,
        "publication_complete": bool(publication_complete),
        "self_check_status": (report.get("self_check") or {}).get("status"),
    })
    history[-1] = snap
    save_history(history, history_path)
    report.setdefault("temporal_analysis", {})["current_snapshot_canonicalized"] = True
    report["temporal_analysis"]["current_snapshot_publication_complete"] = bool(publication_complete)
    return {
        "synced": True, "generated_at": generated_at, "final_primary_score": score,
        "score_contract": HISTORY_CONTRACT, "report_version": VERSION,
        "decision_model": snap.get("decision_model"), "publication_complete": bool(publication_complete),
    }


def validate_current_decision_snapshot(report, history_path=None):
    history_path = history_path or base._history_path_default()
    history = load_history(history_path)
    generated_at = str((report or {}).get("generated_at") or "")
    if not history or str(history[-1].get("generated_at") or "") != generated_at:
        return {"valid": False, "reason": "current_snapshot_not_found"}
    snap = history[-1]
    current = base._int(((report or {}).get("scores") or {}).get("global"), 0)
    valid = (
        snap.get("score_contract") == HISTORY_CONTRACT
        and base._int(snap.get("final_primary_score")) == current
        and base._int(snap.get("health_score_v3")) == current
        and str(snap.get("report_version") or "") == VERSION
        and str(snap.get("report_schema") or "") == REPORT_SCHEMA
        and str(snap.get("action_plan_model") or "") == ACTION_PLAN_MODEL
        and str(snap.get("diagnostic_source") or "") == ACTION_PLAN_SOURCE
        and str(snap.get("decision_model") or "") == DECISION_MODEL
        and str(snap.get("condition_model") or "") == CONDITION_MODEL
    )
    return {
        "valid": bool(valid), "score_contract": snap.get("score_contract"),
        "final_primary_score": snap.get("final_primary_score"), "report_version": snap.get("report_version"),
        "report_schema": snap.get("report_schema"), "action_plan_model": snap.get("action_plan_model"),
        "diagnostic_source": snap.get("diagnostic_source"), "decision_model": snap.get("decision_model"),
        "condition_model": snap.get("condition_model"), "publication_complete": bool(snap.get("publication_complete")),
    }
