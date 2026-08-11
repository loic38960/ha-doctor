"""HA Doctor 0.16 published-baseline visibility and current-contract transaction."""

from temporal_v060 import load_history, save_history
import temporal_v083 as temporal_base
import temporal_v150 as base
from contracts_v160 import (
    VERSION, REPORT_SCHEMA, TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL,
    ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE, DECISION_MODEL, CONDITION_MODEL,
)


def _history_path_default():
    return base._history_path_default()


def _int(value, default=None):
    try:
        if value is None: return default
        return int(value)
    except Exception:
        return default


def _published(snapshot):
    return (
        isinstance(snapshot, dict)
        and snapshot.get("publication_complete") is True
        and snapshot.get("score_contract") == HISTORY_CONTRACT
        and snapshot.get("final_primary_score") is not None
    )


def _latest_published(history, generated_at=None):
    for snap in reversed(history or []):
        if generated_at and str(snap.get("generated_at") or "") == str(generated_at):
            continue
        if _published(snap): return snap
    return None


def _age_seconds(generated_at, previous_at):
    current = temporal_base._parse_ts(str(generated_at or "")); previous = temporal_base._parse_ts(str(previous_at or ""))
    if not current or not previous: return None
    return max(0, int((current - previous).total_seconds()))


def apply_temporal_truth_v7(report, history_path=None, min_interval_seconds=15 * 60):
    history_path = history_path or _history_path_default()
    temporal = base.apply_temporal_truth_v6(report, history_path=history_path, min_interval_seconds=min_interval_seconds)
    history = load_history(history_path)
    latest = _latest_published(history, report.get("generated_at"))
    age = _age_seconds(report.get("generated_at"), (latest or {}).get("generated_at")) if latest else None
    temporal.update({
        "model": TEMPORAL_MODEL,
        "history_contract": HISTORY_CONTRACT, "history_policy": HISTORY_POLICY, "publication_model": PUBLICATION_MODEL,
        "latest_published_baseline_generated_at": (latest or {}).get("generated_at"),
        "latest_published_baseline_score": (latest or {}).get("final_primary_score"),
        "latest_published_baseline_report_version": (latest or {}).get("report_version"),
        "latest_published_baseline_age_seconds": age,
        "latest_published_baseline_eligible_for_delta": bool(latest and age is not None and age >= min_interval_seconds),
        "current_committed_baseline": False,
        "canonical_published_including_current": sum(1 for x in history[-10:] if _published(x)),
        "baseline_visibility_independent_of_delta_eligibility": True,
    })
    report["temporal_analysis"] = temporal
    report.setdefault("score_history_integrity", {}).update({
        "model": "score_history_integrity_v4_baseline_visibility",
        "latest_published_baseline_generated_at": temporal.get("latest_published_baseline_generated_at"),
        "latest_published_baseline_score": temporal.get("latest_published_baseline_score"),
        "canonical_published_including_current": temporal.get("canonical_published_including_current", 0),
        "current_committed_baseline": False,
    })
    return temporal


def _update_current_snapshot(report, history_path, publish, phase):
    history = load_history(history_path); generated_at = str((report or {}).get("generated_at") or "")
    if not history or str(history[-1].get("generated_at") or "") != generated_at:
        return {"synced": False, "reason": "current_snapshot_not_found"}
    score = _int(((report or {}).get("scores") or {}).get("global"), 0)
    preview = _int(((report or {}).get("score_v5_preview") or {}).get("v5_preview_score"), score)
    snap = dict(history[-1])
    snap.update({
        "report_version": VERSION, "report_schema": REPORT_SCHEMA, "temporal_model": TEMPORAL_MODEL,
        "history_policy": HISTORY_POLICY, "publication_model": PUBLICATION_MODEL,
        "action_plan_model": ((report or {}).get("action_plan") or {}).get("model") or ACTION_PLAN_MODEL,
        "diagnostic_source": ((report or {}).get("diagnostic_summary") or {}).get("source") or ACTION_PLAN_SOURCE,
        "decision_model": ((report or {}).get("decision_engine") or {}).get("model") or DECISION_MODEL,
        "condition_model": ((report or {}).get("condition_semantics") or {}).get("model") or CONDITION_MODEL,
        "self_check_status": ((report or {}).get("self_check") or {}).get("status"),
        "publication_complete": bool(publish), "candidate_primary_score": score,
        "publication_transaction": phase,
    })
    if publish:
        snap.update({
            "health_score_v3": score, "final_primary_score": score, "final_preview_score": preview,
            "score_contract": HISTORY_CONTRACT, "history_role": "published_canonical",
        })
    else:
        for key in ("score_contract", "final_primary_score", "final_preview_score"):
            snap.pop(key, None)
        snap["history_role"] = "publication_candidate" if phase == "staged" else "blocked_or_unpublished_candidate"
    history[-1] = snap; save_history(history, history_path)
    return {
        "synced": True, "generated_at": generated_at, "publication_complete": bool(publish),
        "history_role": snap.get("history_role"), "score_contract": snap.get("score_contract"),
        "report_version": VERSION, "phase": phase,
    }


def stage_publication(report, history_path=None):
    history_path = history_path or _history_path_default(); result = _update_current_snapshot(report, history_path, False, "staged")
    report.setdefault("temporal_analysis", {})["publication_phase"] = "staged"
    report["temporal_analysis"]["current_snapshot_publication_complete"] = False
    report["temporal_analysis"]["current_committed_baseline"] = False
    report["publication_transaction"] = {"model": PUBLICATION_MODEL, "phase": "staged", "committed": False, "history_sync": result}
    return result


def commit_publication(report, history_path=None):
    history_path = history_path or _history_path_default(); result = _update_current_snapshot(report, history_path, True, "committed")
    report.setdefault("temporal_analysis", {})["publication_phase"] = "committed"
    report["temporal_analysis"]["current_snapshot_publication_complete"] = True
    report["publication_transaction"] = {"model": PUBLICATION_MODEL, "phase": "committed", "committed": True, "history_sync": result}
    return result


def abort_publication(report, history_path=None, reason="validation_failed"):
    history_path = history_path or _history_path_default(); result = _update_current_snapshot(report, history_path, False, "aborted")
    report.setdefault("temporal_analysis", {})["publication_phase"] = "aborted"
    report["temporal_analysis"]["current_snapshot_publication_complete"] = False
    report["temporal_analysis"]["current_committed_baseline"] = False
    report["publication_transaction"] = {"model": PUBLICATION_MODEL, "phase": "aborted", "committed": False, "reason": reason, "history_sync": result}
    return result


def validate_current_snapshot(report, history_path=None, require_published=True):
    history_path = history_path or _history_path_default(); history = load_history(history_path)
    generated_at = str((report or {}).get("generated_at") or "")
    if not history or str(history[-1].get("generated_at") or "") != generated_at:
        return {"valid": False, "reason": "current_snapshot_not_found"}
    snap = history[-1]
    identity = (
        str(snap.get("report_version") or "") == VERSION
        and str(snap.get("report_schema") or "") == REPORT_SCHEMA
        and str(snap.get("action_plan_model") or "") == ACTION_PLAN_MODEL
        and str(snap.get("diagnostic_source") or "") == ACTION_PLAN_SOURCE
        and str(snap.get("decision_model") or "") == DECISION_MODEL
        and str(snap.get("condition_model") or "") == CONDITION_MODEL
        and str(snap.get("publication_model") or "") == PUBLICATION_MODEL
    )
    current = _int(((report or {}).get("scores") or {}).get("global"), 0)
    if require_published:
        valid = identity and snap.get("publication_complete") is True and snap.get("score_contract") == HISTORY_CONTRACT and _int(snap.get("final_primary_score")) == current
    else:
        valid = identity and snap.get("publication_complete") is False and snap.get("score_contract") is None and snap.get("final_primary_score") is None
    return {
        "valid": bool(valid), "publication_complete": bool(snap.get("publication_complete")),
        "score_contract": snap.get("score_contract"), "final_primary_score": snap.get("final_primary_score"),
        "candidate_primary_score": snap.get("candidate_primary_score"), "history_role": snap.get("history_role"),
        "publication_transaction": snap.get("publication_transaction"), "report_version": snap.get("report_version"),
    }


def refresh_published_baseline_visibility(report, history_path=None):
    history_path = history_path or _history_path_default(); history = load_history(history_path)
    current_at = str(report.get("generated_at") or "")
    current = history[-1] if history and str(history[-1].get("generated_at") or "") == current_at else None
    committed = bool(current and _published(current)); canonical_count = sum(1 for x in history[-10:] if _published(x)); latest = _latest_published(history, None)
    temporal = report.setdefault("temporal_analysis", {})
    temporal.update({
        "model": TEMPORAL_MODEL, "current_committed_baseline": committed,
        "current_snapshot_publication_complete": committed, "canonical_published_including_current": canonical_count,
        "latest_published_score_including_current": (latest or {}).get("final_primary_score"),
        "latest_published_generated_at_including_current": (latest or {}).get("generated_at"),
        "next_scan_baseline_candidate_score": (current or {}).get("final_primary_score") if committed else None,
        "next_scan_baseline_candidate_generated_at": current_at if committed else None,
    })
    report.setdefault("score_history_integrity", {}).update({
        "model": "score_history_integrity_v4_baseline_visibility", "current_committed_baseline": committed,
        "canonical_published_including_current": canonical_count,
        "latest_published_score_including_current": temporal.get("latest_published_score_including_current"),
    })
    return {"current_committed_baseline": committed, "canonical_published_including_current": canonical_count, "next_scan_baseline_candidate_score": temporal.get("next_scan_baseline_candidate_score")}


def validate_current_publication_snapshot(report, history_path=None, require_published=True):
    return validate_current_snapshot(report, history_path=history_path, require_published=require_published)
