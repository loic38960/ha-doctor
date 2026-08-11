"""Canonical temporal score history for HA Doctor 0.12.

0.12 never guesses the published score of a legacy snapshot. Only snapshots
explicitly stamped with published_primary_score_v1 may be used for score deltas.
"""

from temporal_v060 import HISTORY_LIMIT, load_history, save_history
import temporal_v083 as temporal_base
from contracts_v120 import (
    VERSION, REPORT_SCHEMA, TEMPORAL_MODEL, HISTORY_CONTRACT,
    ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE,
)


def _int(value, default=None):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _canonical_snapshot_score(snapshot):
    if not isinstance(snapshot, dict):
        return None, "missing", False
    if snapshot.get("score_contract") == HISTORY_CONTRACT and snapshot.get("final_primary_score") is not None:
        return _int(snapshot.get("final_primary_score")), "final_primary_score", True
    return _int(snapshot.get("health_score_v3")), "legacy_intermediate_health_score_v3", False


def _history_path_default():
    try:
        import intelligence_v088 as intelligence
        return intelligence.v087.HISTORY_PATH
    except Exception:
        return "/data/ha-doctor-history.json"


def _meaningful_previous(history, generated_at, min_interval_seconds):
    current_ts = temporal_base._parse_ts(generated_at)
    if current_ts:
        return temporal_base._meaningful_previous(history, current_ts, min_interval_seconds)
    return history[-1] if history else None


def apply_temporal_truth_v4(report, history_path=None, min_interval_seconds=15 * 60):
    if not isinstance(report, dict):
        return {}
    history_path = history_path or _history_path_default()
    full_history = load_history(history_path)
    generated_at = str(report.get("generated_at") or "")
    history = [x for x in full_history if str(x.get("generated_at") or "") != generated_at]
    previous = _meaningful_previous(history, generated_at, min_interval_seconds)
    current = _int((report.get("scores") or {}).get("global"), 0)
    candidate, source, trusted = _canonical_snapshot_score(previous)
    previous_score = candidate if trusted else None
    delta = current - previous_score if trusted and previous_score is not None else None

    points = []
    canonical = legacy = 0
    for snap in history[-10:]:
        score, item_source, item_trusted = _canonical_snapshot_score(snap)
        if item_trusted:
            canonical += 1
            points.append({"generated_at": snap.get("generated_at"), "score": score, "trusted": True, "source": item_source})
        else:
            legacy += 1
            points.append({"generated_at": snap.get("generated_at"), "score": None, "trusted": False, "legacy_candidate": score, "source": item_source})

    status = "canonical" if trusted else ("legacy_untrusted" if previous else "baseline")
    temporal = report.setdefault("temporal_analysis", {})
    temporal.update({
        "enabled": True,
        "model": TEMPORAL_MODEL,
        "history_limit": HISTORY_LIMIT,
        "minimum_persistence_interval_seconds": min_interval_seconds,
        "meaningful_previous_generated_at": previous.get("generated_at") if previous else None,
        "previous_score": previous_score,
        "score_delta": delta,
        "previous_score_trusted": trusted,
        "previous_score_source": source,
        "legacy_previous_score_candidate": candidate if previous and not trusted else None,
        "current_primary_score": current,
        "current_score_source": "final_report_primary_score",
        "score_comparison_status": status,
        "score_history": points,
        "canonical_score_history": True,
        "legacy_scores_never_guessed": True,
        "false_stability_prevented": bool(previous and not trusted),
        "history_contract": HISTORY_CONTRACT,
        "history_migration_mode": "forward_only_no_guessing",
        "canonical_score_history_snapshot_count_last_10": canonical,
        "legacy_untrusted_snapshot_count_last_10": legacy,
    })
    report["score_history_integrity"] = {
        "model": "score_history_integrity_v1",
        "contract": HISTORY_CONTRACT,
        "comparison_status": status,
        "previous_score_trusted": trusted,
        "legacy_previous_score_candidate": candidate if previous and not trusted else None,
        "false_stability_prevented": bool(previous and not trusted),
        "canonical_snapshots_last_10": canonical,
        "legacy_untrusted_snapshots_last_10": legacy,
        "migration": "forward_only_no_guessing",
    }
    report.setdefault("privacy", {}).update({
        "temporal_v4_additional_home_assistant_state_reads": 0,
        "temporal_v4_raw_states_persisted": False,
        "temporal_v4_raw_yaml_persisted": False,
        "temporal_v4_secret_values_persisted": False,
        "temporal_history_scope": "diagnostic_ids_counts_final_scores_timestamps_contract_metadata_only",
    })
    return temporal


def sync_canonical_history(report, history_path=None, publication_complete=False):
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
        "health_score_v3": score,
        "final_primary_score": score,
        "final_preview_score": preview,
        "score_contract": HISTORY_CONTRACT,
        "report_version": VERSION,
        "report_schema": REPORT_SCHEMA,
        "temporal_model": TEMPORAL_MODEL,
        "action_plan_model": (report.get("action_plan") or {}).get("model") or ACTION_PLAN_MODEL,
        "diagnostic_source": (report.get("diagnostic_summary") or {}).get("source") or ACTION_PLAN_SOURCE,
        "publication_complete": bool(publication_complete),
        "self_check_status": (report.get("self_check") or {}).get("status"),
    })
    history[-1] = snap
    save_history(history, history_path)
    report.setdefault("temporal_analysis", {})["current_snapshot_canonicalized"] = True
    report["temporal_analysis"]["current_snapshot_publication_complete"] = bool(publication_complete)
    return {"synced": True, "generated_at": generated_at, "final_primary_score": score, "score_contract": HISTORY_CONTRACT, "publication_complete": bool(publication_complete)}


def validate_current_canonical_snapshot(report, history_path=None):
    history_path = history_path or _history_path_default()
    history = load_history(history_path)
    generated_at = str((report or {}).get("generated_at") or "")
    if not history or str(history[-1].get("generated_at") or "") != generated_at:
        return {"valid": False, "reason": "current_snapshot_not_found"}
    snap = history[-1]
    current = _int(((report or {}).get("scores") or {}).get("global"), 0)
    valid = (
        snap.get("score_contract") == HISTORY_CONTRACT
        and _int(snap.get("final_primary_score")) == current
        and _int(snap.get("health_score_v3")) == current
        and str(snap.get("report_version") or "") == VERSION
    )
    return {"valid": bool(valid), "score_contract": snap.get("score_contract"), "final_primary_score": snap.get("final_primary_score"), "compatibility_score": snap.get("health_score_v3"), "publication_complete": bool(snap.get("publication_complete"))}
