"""HA Doctor 0.14 publication-aware canonical score history.

A score snapshot is trusted only when it carries the existing
published_primary_score_v1 contract *and* publication_complete is true. A report
blocked by Self-Check can therefore never become the baseline of the next scan.
"""

from temporal_v060 import HISTORY_LIMIT, load_history, save_history
import temporal_v083 as temporal_base
import temporal_v120 as legacy
from contracts_v140 import (
    VERSION, REPORT_SCHEMA, TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY,
    ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE, DECISION_MODEL, CONDITION_MODEL,
)


def _int(value, default=None):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _history_path_default():
    return legacy._history_path_default()


def _snapshot_status(snapshot):
    if not isinstance(snapshot, dict):
        return {"trusted": False, "score": None, "status": "missing", "source": "missing"}
    score = _int(snapshot.get("final_primary_score"), _int(snapshot.get("health_score_v3")))
    has_contract = snapshot.get("score_contract") == HISTORY_CONTRACT
    published = snapshot.get("publication_complete") is True
    if has_contract and published and snapshot.get("final_primary_score") is not None:
        return {"trusted": True, "score": _int(snapshot.get("final_primary_score")), "status": "canonical_published", "source": "final_primary_score"}
    if has_contract and not published:
        return {"trusted": False, "score": score, "status": "blocked_unpublished", "source": "blocked_canonical_candidate"}
    return {"trusted": False, "score": score, "status": "legacy_untrusted", "source": "legacy_intermediate_health_score_v3"}


def _eligible_previous(history, generated_at, min_interval_seconds):
    current_ts = temporal_base._parse_ts(generated_at)
    if not history:
        return None
    if not current_ts:
        for snap in reversed(history):
            if _snapshot_status(snap)["trusted"]:
                return snap
        return None
    for snap in reversed(history):
        ts = temporal_base._parse_ts(str(snap.get("generated_at") or ""))
        if not ts:
            continue
        if (current_ts - ts).total_seconds() < min_interval_seconds:
            continue
        if _snapshot_status(snap)["trusted"]:
            return snap
    return None


def _latest_meaningful_candidate(history, generated_at, min_interval_seconds):
    current_ts = temporal_base._parse_ts(generated_at)
    if current_ts:
        return temporal_base._meaningful_previous(history, current_ts, min_interval_seconds)
    return history[-1] if history else None


def apply_temporal_truth_v5(report, history_path=None, min_interval_seconds=15 * 60):
    if not isinstance(report, dict):
        return {}
    history_path = history_path or _history_path_default()
    full_history = load_history(history_path)
    generated_at = str(report.get("generated_at") or "")
    history = [x for x in full_history if str(x.get("generated_at") or "") != generated_at]
    candidate = _latest_meaningful_candidate(history, generated_at, min_interval_seconds)
    previous = _eligible_previous(history, generated_at, min_interval_seconds)
    previous_status = _snapshot_status(previous)
    candidate_status = _snapshot_status(candidate)
    current = _int((report.get("scores") or {}).get("global"), 0)
    previous_score = previous_status["score"] if previous_status["trusted"] else None
    delta = current - previous_score if previous_score is not None else None

    canonical = blocked = legacy_count = 0
    points = []
    for snap in history[-10:]:
        status = _snapshot_status(snap)
        if status["status"] == "canonical_published": canonical += 1
        elif status["status"] == "blocked_unpublished": blocked += 1
        else: legacy_count += 1
        points.append({
            "generated_at": snap.get("generated_at"),
            "score": status["score"] if status["trusted"] else None,
            "trusted": status["trusted"], "status": status["status"],
        })

    if previous_status["trusted"]:
        comparison_status = "canonical"
    elif candidate_status["status"] == "blocked_unpublished":
        comparison_status = "blocked_previous_ignored"
    elif candidate:
        comparison_status = "legacy_untrusted"
    else:
        comparison_status = "baseline"

    temporal = report.setdefault("temporal_analysis", {})
    temporal.update({
        "enabled": True, "model": TEMPORAL_MODEL, "history_limit": HISTORY_LIMIT,
        "minimum_persistence_interval_seconds": min_interval_seconds,
        "meaningful_previous_generated_at": previous.get("generated_at") if previous else None,
        "latest_candidate_generated_at": candidate.get("generated_at") if candidate else None,
        "previous_score": previous_score, "score_delta": delta,
        "previous_score_trusted": bool(previous_status["trusted"]),
        "previous_score_source": previous_status["source"],
        "latest_candidate_status": candidate_status["status"] if candidate else None,
        "legacy_previous_score_candidate": candidate_status["score"] if candidate and not candidate_status["trusted"] else None,
        "current_primary_score": current, "current_score_source": "final_report_primary_score",
        "score_comparison_status": comparison_status,
        "score_history": points, "canonical_score_history": True,
        "publication_complete_required_for_trust": True,
        "blocked_reports_never_become_score_baselines": True,
        "false_stability_prevented": bool(candidate and not candidate_status["trusted"] and not previous_status["trusted"]),
        "history_contract": HISTORY_CONTRACT, "history_policy": HISTORY_POLICY,
        "history_migration_mode": "forward_only_publication_aware",
        "canonical_published_snapshots_last_10": canonical,
        "blocked_unpublished_snapshots_last_10": blocked,
        "legacy_untrusted_snapshots_last_10": legacy_count,
    })
    report["score_history_integrity"] = {
        "model": "score_history_integrity_v2_publication_aware", "contract": HISTORY_CONTRACT,
        "policy": HISTORY_POLICY, "comparison_status": comparison_status,
        "previous_score_trusted": bool(previous_status["trusted"]),
        "latest_candidate_status": candidate_status["status"] if candidate else None,
        "false_stability_prevented": temporal["false_stability_prevented"],
        "canonical_published_snapshots_last_10": canonical,
        "blocked_unpublished_snapshots_last_10": blocked,
        "legacy_untrusted_snapshots_last_10": legacy_count,
    }
    report.setdefault("privacy", {}).update({
        "temporal_v5_additional_home_assistant_state_reads": 0,
        "temporal_v5_raw_states_persisted": False,
        "temporal_v5_raw_yaml_persisted": False,
        "temporal_v5_secret_values_persisted": False,
        "temporal_history_scope": "diagnostic_ids_counts_final_scores_timestamps_publication_metadata_only",
    })
    return temporal


def sync_publication_history(report, history_path=None, publication_complete=False):
    if not isinstance(report, dict):
        return {"synced": False, "reason": "report_not_object"}
    history_path = history_path or _history_path_default()
    history = load_history(history_path)
    generated_at = str(report.get("generated_at") or "")
    if not history or str(history[-1].get("generated_at") or "") != generated_at:
        return {"synced": False, "reason": "current_snapshot_not_found"}
    score = _int((report.get("scores") or {}).get("global"), 0)
    preview = _int((report.get("score_v5_preview") or {}).get("v5_preview_score"), score)
    snap = dict(history[-1])
    snap.update({
        "report_version": VERSION, "report_schema": REPORT_SCHEMA,
        "temporal_model": TEMPORAL_MODEL, "history_policy": HISTORY_POLICY,
        "action_plan_model": (report.get("action_plan") or {}).get("model") or ACTION_PLAN_MODEL,
        "diagnostic_source": (report.get("diagnostic_summary") or {}).get("source") or ACTION_PLAN_SOURCE,
        "decision_model": (report.get("decision_engine") or {}).get("model") or DECISION_MODEL,
        "condition_model": (report.get("condition_semantics") or {}).get("model") or CONDITION_MODEL,
        "self_check_status": (report.get("self_check") or {}).get("status"),
        "publication_complete": bool(publication_complete),
    })
    if publication_complete:
        snap.update({
            "health_score_v3": score, "final_primary_score": score,
            "final_preview_score": preview, "score_contract": HISTORY_CONTRACT,
            "history_role": "published_canonical",
        })
    else:
        for key in ("score_contract", "final_primary_score", "final_preview_score"):
            snap.pop(key, None)
        snap.update({"candidate_primary_score": score, "history_role": "blocked_or_unpublished_candidate"})
    history[-1] = snap
    save_history(history, history_path)
    report.setdefault("temporal_analysis", {})["current_snapshot_canonicalized"] = bool(publication_complete)
    report["temporal_analysis"]["current_snapshot_publication_complete"] = bool(publication_complete)
    return {
        "synced": True, "generated_at": generated_at, "score": score,
        "score_contract": HISTORY_CONTRACT if publication_complete else None,
        "history_role": snap.get("history_role"), "publication_complete": bool(publication_complete),
    }


def validate_current_publication_snapshot(report, history_path=None, require_published=True):
    history_path = history_path or _history_path_default()
    history = load_history(history_path)
    generated_at = str((report or {}).get("generated_at") or "")
    if not history or str(history[-1].get("generated_at") or "") != generated_at:
        return {"valid": False, "reason": "current_snapshot_not_found"}
    snap = history[-1]; current = _int(((report or {}).get("scores") or {}).get("global"), 0)
    identity = (
        str(snap.get("report_version") or "") == VERSION
        and str(snap.get("report_schema") or "") == REPORT_SCHEMA
        and str(snap.get("action_plan_model") or "") == ACTION_PLAN_MODEL
        and str(snap.get("diagnostic_source") or "") == ACTION_PLAN_SOURCE
        and str(snap.get("decision_model") or "") == DECISION_MODEL
        and str(snap.get("condition_model") or "") == CONDITION_MODEL
    )
    if require_published:
        valid = identity and snap.get("publication_complete") is True and snap.get("score_contract") == HISTORY_CONTRACT and _int(snap.get("final_primary_score")) == current
    else:
        valid = identity and snap.get("publication_complete") is False and snap.get("score_contract") is None and snap.get("final_primary_score") is None
    return {
        "valid": bool(valid), "publication_complete": bool(snap.get("publication_complete")),
        "score_contract": snap.get("score_contract"), "final_primary_score": snap.get("final_primary_score"),
        "candidate_primary_score": snap.get("candidate_primary_score"), "history_role": snap.get("history_role"),
        "report_version": snap.get("report_version"),
    }
