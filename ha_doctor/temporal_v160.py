"""HA Doctor 0.16 published-baseline visibility.

Temporal V7 keeps the publication transaction and anti-rapid-rescan rules from
0.15, while making the latest actually published score visible even when it is
too recent to qualify for a delta. After commit, the current report also shows
that it has become a canonical baseline for the next eligible scan.
"""

from temporal_v060 import load_history
import temporal_v083 as temporal_base
import temporal_v150 as base
from contracts_v160 import VERSION, REPORT_SCHEMA, TEMPORAL_MODEL, HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL


def _history_path_default():
    return base._history_path_default()


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
        if _published(snap):
            return snap
    return None


def _age_seconds(generated_at, previous_at):
    current = temporal_base._parse_ts(str(generated_at or ""))
    previous = temporal_base._parse_ts(str(previous_at or ""))
    if not current or not previous:
        return None
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
    integrity = report.setdefault("score_history_integrity", {})
    integrity.update({
        "model": "score_history_integrity_v4_baseline_visibility",
        "latest_published_baseline_generated_at": temporal.get("latest_published_baseline_generated_at"),
        "latest_published_baseline_score": temporal.get("latest_published_baseline_score"),
        "canonical_published_including_current": temporal.get("canonical_published_including_current", 0),
        "current_committed_baseline": False,
    })
    return temporal


def stage_publication(report, history_path=None):
    return base.stage_publication(report, history_path=history_path)


def commit_publication(report, history_path=None):
    return base.commit_publication(report, history_path=history_path)


def abort_publication(report, history_path=None, reason="validation_failed"):
    return base.abort_publication(report, history_path=history_path, reason=reason)


def validate_current_snapshot(report, history_path=None, require_published=True):
    return base.validate_current_snapshot(report, history_path=history_path, require_published=require_published)


def refresh_published_baseline_visibility(report, history_path=None):
    history_path = history_path or _history_path_default()
    history = load_history(history_path)
    current_at = str(report.get("generated_at") or "")
    current = history[-1] if history and str(history[-1].get("generated_at") or "") == current_at else None
    committed = bool(current and _published(current))
    canonical_count = sum(1 for x in history[-10:] if _published(x))
    latest = _latest_published(history, None)
    temporal = report.setdefault("temporal_analysis", {})
    temporal.update({
        "model": TEMPORAL_MODEL,
        "current_committed_baseline": committed,
        "current_snapshot_publication_complete": committed,
        "canonical_published_including_current": canonical_count,
        "latest_published_score_including_current": (latest or {}).get("final_primary_score"),
        "latest_published_generated_at_including_current": (latest or {}).get("generated_at"),
        "next_scan_baseline_candidate_score": (current or {}).get("final_primary_score") if committed else None,
        "next_scan_baseline_candidate_generated_at": current_at if committed else None,
    })
    report.setdefault("score_history_integrity", {}).update({
        "model": "score_history_integrity_v4_baseline_visibility",
        "current_committed_baseline": committed,
        "canonical_published_including_current": canonical_count,
        "latest_published_score_including_current": temporal.get("latest_published_score_including_current"),
    })
    return {
        "current_committed_baseline": committed,
        "canonical_published_including_current": canonical_count,
        "next_scan_baseline_candidate_score": temporal.get("next_scan_baseline_candidate_score"),
    }


def validate_current_publication_snapshot(report, history_path=None, require_published=True):
    return validate_current_snapshot(report, history_path=history_path, require_published=require_published)
