"""HA Doctor 0.15 two-phase publication transaction for score history."""

from temporal_v060 import HISTORY_LIMIT, load_history, save_history
import temporal_v083 as temporal_base
import temporal_v120 as legacy
from contracts_v150 import (
    VERSION, REPORT_SCHEMA, TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY,
    PUBLICATION_MODEL, ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE, DECISION_MODEL, CONDITION_MODEL,
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
    score = _int(snapshot.get("final_primary_score"), _int(snapshot.get("candidate_primary_score"), _int(snapshot.get("health_score_v3"))))
    canonical = snapshot.get("score_contract") == HISTORY_CONTRACT and snapshot.get("publication_complete") is True and snapshot.get("final_primary_score") is not None
    if canonical:
        return {"trusted": True, "score": _int(snapshot.get("final_primary_score")), "status": "canonical_published", "source": "final_primary_score"}
    if snapshot.get("publication_complete") is False or snapshot.get("history_role") in {"publication_candidate", "blocked_or_unpublished_candidate"}:
        return {"trusted": False, "score": score, "status": "blocked_unpublished", "source": "publication_candidate"}
    return {"trusted": False, "score": score, "status": "legacy_untrusted", "source": "legacy_intermediate_health_score_v3"}


def _eligible_previous(history, generated_at, min_interval_seconds):
    current_ts = temporal_base._parse_ts(generated_at)
    for snap in reversed(history or []):
        status = _snapshot_status(snap)
        if not status["trusted"]:
            continue
        if current_ts:
            ts = temporal_base._parse_ts(str(snap.get("generated_at") or ""))
            if not ts or (current_ts - ts).total_seconds() < min_interval_seconds:
                continue
        return snap
    return None


def _meaningful_candidate(history, generated_at, min_interval_seconds):
    current_ts = temporal_base._parse_ts(generated_at)
    if current_ts:
        return temporal_base._meaningful_previous(history, current_ts, min_interval_seconds)
    return history[-1] if history else None


def apply_temporal_truth_v6(report, history_path=None, min_interval_seconds=15 * 60):
    history_path = history_path or _history_path_default()
    full = load_history(history_path)
    generated_at = str((report or {}).get("generated_at") or "")
    history = [x for x in full if str(x.get("generated_at") or "") != generated_at]
    candidate = _meaningful_candidate(history, generated_at, min_interval_seconds)
    previous = _eligible_previous(history, generated_at, min_interval_seconds)
    prev_status = _snapshot_status(previous)
    candidate_status = _snapshot_status(candidate)
    current = _int(((report or {}).get("scores") or {}).get("global"), 0)
    previous_score = prev_status["score"] if prev_status["trusted"] else None
    delta = current - previous_score if previous_score is not None else None

    counts = {"canonical_published": 0, "blocked_unpublished": 0, "legacy_untrusted": 0}
    points = []
    for snap in history[-10:]:
        status = _snapshot_status(snap)
        counts[status["status"]] = counts.get(status["status"], 0) + 1
        points.append({"generated_at": snap.get("generated_at"), "score": status["score"] if status["trusted"] else None, "trusted": status["trusted"], "status": status["status"]})

    if prev_status["trusted"]:
        comparison = "canonical"
    elif candidate_status["status"] == "blocked_unpublished":
        comparison = "blocked_previous_ignored"
    elif candidate:
        comparison = "legacy_untrusted"
    else:
        comparison = "baseline"

    temporal = report.setdefault("temporal_analysis", {})
    temporal.update({
        "enabled": True, "model": TEMPORAL_MODEL, "history_limit": HISTORY_LIMIT,
        "minimum_persistence_interval_seconds": min_interval_seconds,
        "meaningful_previous_generated_at": previous.get("generated_at") if previous else None,
        "latest_candidate_generated_at": candidate.get("generated_at") if candidate else None,
        "previous_score": previous_score, "score_delta": delta,
        "previous_score_trusted": bool(prev_status["trusted"]), "previous_score_source": prev_status["source"],
        "latest_candidate_status": candidate_status["status"] if candidate else None,
        "current_primary_score": current, "current_score_source": "final_report_primary_score",
        "score_comparison_status": comparison, "score_history": points,
        "canonical_score_history": True, "publication_complete_required_for_trust": True,
        "blocked_reports_never_become_score_baselines": True,
        "false_stability_prevented": bool(candidate and not candidate_status["trusted"] and not prev_status["trusted"]),
        "history_contract": HISTORY_CONTRACT, "history_policy": HISTORY_POLICY,
        "publication_model": PUBLICATION_MODEL, "publication_phase": "preflight",
        "history_migration_mode": "forward_only_publication_transaction",
        "canonical_published_snapshots_last_10": counts.get("canonical_published", 0),
        "blocked_unpublished_snapshots_last_10": counts.get("blocked_unpublished", 0),
        "legacy_untrusted_snapshots_last_10": counts.get("legacy_untrusted", 0),
    })
    report["score_history_integrity"] = {
        "model": "score_history_integrity_v3_publication_transaction", "contract": HISTORY_CONTRACT,
        "policy": HISTORY_POLICY, "publication_model": PUBLICATION_MODEL,
        "comparison_status": comparison, "previous_score_trusted": bool(prev_status["trusted"]),
        "latest_candidate_status": candidate_status["status"] if candidate else None,
        "false_stability_prevented": temporal["false_stability_prevented"],
        "canonical_published_snapshots_last_10": counts.get("canonical_published", 0),
        "blocked_unpublished_snapshots_last_10": counts.get("blocked_unpublished", 0),
        "legacy_untrusted_snapshots_last_10": counts.get("legacy_untrusted", 0),
    }
    return temporal


def _update_current_snapshot(report, history_path, publish):
    history = load_history(history_path)
    generated_at = str((report or {}).get("generated_at") or "")
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
        "publication_transaction": "committed" if publish else "staged",
    })
    if publish:
        snap.update({
            "health_score_v3": score, "final_primary_score": score, "final_preview_score": preview,
            "score_contract": HISTORY_CONTRACT, "history_role": "published_canonical",
        })
    else:
        for key in ("score_contract", "final_primary_score", "final_preview_score"):
            snap.pop(key, None)
        snap["history_role"] = "publication_candidate"
    history[-1] = snap
    save_history(history, history_path)
    return {"synced": True, "generated_at": generated_at, "publication_complete": bool(publish), "history_role": snap.get("history_role"), "score_contract": snap.get("score_contract")}


def stage_publication(report, history_path=None):
    history_path = history_path or _history_path_default()
    result = _update_current_snapshot(report, history_path, publish=False)
    report.setdefault("temporal_analysis", {})["publication_phase"] = "staged"
    report["temporal_analysis"]["current_snapshot_publication_complete"] = False
    report["publication_transaction"] = {"model": PUBLICATION_MODEL, "phase": "staged", "committed": False, "history_sync": result}
    return result


def commit_publication(report, history_path=None):
    history_path = history_path or _history_path_default()
    result = _update_current_snapshot(report, history_path, publish=True)
    report.setdefault("temporal_analysis", {})["publication_phase"] = "committed"
    report["temporal_analysis"]["current_snapshot_publication_complete"] = True
    report["publication_transaction"] = {"model": PUBLICATION_MODEL, "phase": "committed", "committed": True, "history_sync": result}
    return result


def abort_publication(report, history_path=None, reason="self_check_or_release_gate"):
    history_path = history_path or _history_path_default()
    result = _update_current_snapshot(report, history_path, publish=False)
    report.setdefault("temporal_analysis", {})["publication_phase"] = "aborted"
    report["temporal_analysis"]["current_snapshot_publication_complete"] = False
    report["publication_transaction"] = {"model": PUBLICATION_MODEL, "phase": "aborted", "committed": False, "reason": reason, "history_sync": result}
    return result


def validate_current_snapshot(report, history_path=None, require_published=False):
    history_path = history_path or _history_path_default()
    history = load_history(history_path)
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
