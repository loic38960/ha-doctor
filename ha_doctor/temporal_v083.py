"""HA Doctor 0.8.3 duration-qualified temporal analysis.

Temporal V3 keeps the compact privacy-preserving history format, but no longer
lets rapid manual rescans promote a diagnostic to persistent. Persistence is
qualified by elapsed wall-clock time.
"""
from datetime import datetime, timezone

from temporal_v060 import HISTORY_LIMIT, load_history, save_history

VERSION = "0.8.3"
MODEL = "temporal_v3_duration_qualified"
DEFAULT_MIN_INTERVAL_SECONDS = 15 * 60


def _parse_ts(value):
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _seconds(a, b):
    if not a or not b:
        return None
    return max(0.0, (a - b).total_seconds())


def _snapshots_with_id(history, diagnostic_id):
    result = []
    for snap in history:
        if diagnostic_id in set(snap.get("active_ids") or []):
            ts = _parse_ts(snap.get("generated_at"))
            if ts:
                result.append((ts, snap))
    result.sort(key=lambda item: item[0])
    return result


def _qualified_observations(seen, current_ts, min_interval_seconds):
    """Compress repeated scans into meaningful wall-clock observations."""
    times = [item[0] for item in seen]
    if current_ts:
        times.append(current_ts)
    times = sorted(set(times))
    if not times:
        return []
    qualified = [times[0]]
    for ts in times[1:]:
        if (ts - qualified[-1]).total_seconds() >= min_interval_seconds:
            qualified.append(ts)
    return qualified


def _meaningful_previous(history, current_ts, min_interval_seconds):
    if not history:
        return None
    if not current_ts:
        return history[-1]
    threshold = current_ts.timestamp() - min_interval_seconds
    candidates = []
    for snap in history:
        ts = _parse_ts(snap.get("generated_at"))
        if ts and ts.timestamp() <= threshold:
            candidates.append((ts, snap))
    if candidates:
        candidates.sort(key=lambda item: item[0])
        return candidates[-1][1]
    return history[-1]


def _status_for(item, history, current_ts, min_interval_seconds):
    diagnostic_id = str(item.get("id") or "")
    seen = _snapshots_with_id(history, diagnostic_id)
    raw_occurrences = len(seen) + 1
    first_ts = seen[0][0] if seen else current_ts
    last_prior_ts = seen[-1][0] if seen else None
    age_seconds = _seconds(current_ts, first_ts)
    since_last_seconds = _seconds(current_ts, last_prior_ts)
    qualified = _qualified_observations(seen, current_ts, min_interval_seconds)

    previous_ids = set(history[-1].get("active_ids") or []) if history else set()
    previously_active = diagnostic_id in previous_ids
    seen_before = bool(seen)

    if not history:
        status = "baseline"
    elif not seen_before:
        status = "new"
    elif previously_active:
        # A second scan a few seconds later must remain "new/observed", not
        # magically become persistent.
        if age_seconds is not None and age_seconds >= min_interval_seconds and len(qualified) >= 2:
            status = "persistent"
        else:
            status = "new"
    else:
        status = "recurrent"

    source_type = str(item.get("source_type") or "")
    if source_type.startswith("registry_"):
        factor = {
            "baseline": 0.72,
            "new": 0.72,
            "recurrent": 0.86,
            "persistent": 1.0,
        }.get(status, 0.82)
    else:
        factor = {
            "baseline": 0.94,
            "new": 0.94,
            "recurrent": 0.97,
            "persistent": 1.0,
        }.get(status, 1.0)

    rapid_rescan_ignored = bool(
        previously_active
        and since_last_seconds is not None
        and since_last_seconds < min_interval_seconds
        and (age_seconds or 0) < min_interval_seconds
    )

    return {
        "status": status,
        "occurrences": raw_occurrences,
        "consecutive_scans": int((item.get("temporal") or {}).get("consecutive_scans", raw_occurrences) or raw_occurrences),
        "qualified_observations": len(qualified),
        "first_seen": first_ts.isoformat().replace("+00:00", "Z") if first_ts else None,
        "last_seen_before_current": last_prior_ts.isoformat().replace("+00:00", "Z") if last_prior_ts else None,
        "age_seconds": int(age_seconds) if age_seconds is not None else None,
        "seconds_since_previous_observation": int(since_last_seconds) if since_last_seconds is not None else None,
        "minimum_persistence_interval_seconds": min_interval_seconds,
        "rapid_rescan_ignored": rapid_rescan_ignored,
        "persistence_factor": factor,
        "model": MODEL,
    }


def apply_temporal_v3(report, history_path="/data/ha-doctor-history.json", min_interval_seconds=DEFAULT_MIN_INTERVAL_SECONDS):
    full_history = load_history(history_path)
    current_generated_at = str(report.get("generated_at") or "")
    # The legacy temporal layer writes the current snapshot before 0.8.3 runs.
    # Exclude that same snapshot from the evidence set or it would count the
    # current scan as its own previous observation.
    history = [
        snap for snap in full_history
        if str(snap.get("generated_at") or "") != current_generated_at
    ]
    current_ts = _parse_ts(report.get("generated_at")) or datetime.now(timezone.utc)

    explanations = report.get("diagnostic_explanations") or []
    temporal_by_id = {}
    for item in explanations:
        temporal = _status_for(item, history, current_ts, min_interval_seconds)
        item["temporal"] = temporal
        diagnostic_id = str(item.get("id") or "")
        if diagnostic_id:
            temporal_by_id[diagnostic_id] = temporal

    for section_name in ("action_plan", "recommendation_queue"):
        section = report.get(section_name) or {}
        for item in section.get("items") or []:
            diagnostic_id = str(item.get("id") or "")
            if diagnostic_id in temporal_by_id:
                item["temporal"] = dict(temporal_by_id[diagnostic_id])
        if section_name == "action_plan":
            section["top"] = list((section.get("items") or [])[:6])

    plan_items = (report.get("action_plan") or {}).get("items") or []
    current_ids = {str(item.get("id") or "") for item in plan_items if item.get("id")}
    previous = _meaningful_previous(history, current_ts, min_interval_seconds)
    previous_ids = set(previous.get("active_ids") or []) if previous else set()

    new_ids = sorted(
        str(item.get("id"))
        for item in plan_items
        if (item.get("temporal") or {}).get("status") == "new"
    )
    persistent_ids = sorted(
        str(item.get("id"))
        for item in plan_items
        if (item.get("temporal") or {}).get("status") == "persistent"
    )
    recurrent_ids = sorted(
        str(item.get("id"))
        for item in plan_items
        if (item.get("temporal") or {}).get("status") == "recurrent"
    )
    resolved = sorted(previous_ids - current_ids) if previous else []

    legacy = report.get("temporal_analysis") or {}
    report["temporal_analysis"] = {
        **legacy,
        "enabled": True,
        "model": MODEL,
        "history_limit": HISTORY_LIMIT,
        "minimum_persistence_interval_seconds": min_interval_seconds,
        "meaningful_previous_generated_at": previous.get("generated_at") if previous else None,
        "new_count": len(new_ids),
        "persistent_count": len(persistent_ids),
        "recurrent_count": len(recurrent_ids),
        "resolved_since_previous_count": len(resolved),
        "new_ids": new_ids[:20],
        "persistent_ids": persistent_ids[:20],
        "recurrent_ids": recurrent_ids[:20],
        "resolved_since_previous": resolved[:20],
        "rapid_rescan_protection": True,
        "rapid_rescans_promote_persistence": False,
        "scope": "final_action_plan_duration_qualified",
        "note": (
            "Temporal V3 qualifie la persistance avec le temps réel. Des rescans rapprochés "
            "restent visibles mais ne suffisent plus à rendre un diagnostic persistant."
        ),
    }

    # Patch the already-created current history item instead of appending a
    # second snapshot. No raw state values are added.
    history = load_history(history_path)
    if history and str(history[-1].get("generated_at") or "") == str(report.get("generated_at") or ""):
        snap = dict(history[-1])
        snap["report_version"] = VERSION
        snap["temporal_model"] = MODEL
        snap["minimum_persistence_interval_seconds"] = min_interval_seconds
        snap["qualified_new_count"] = len(new_ids)
        snap["qualified_persistent_count"] = len(persistent_ids)
        snap["qualified_recurrent_count"] = len(recurrent_ids)
        history[-1] = snap
        save_history(history, history_path)

    report.setdefault("privacy", {}).update({
        "temporal_history_raw_states_persisted": False,
        "temporal_history_secret_values_persisted": False,
        "temporal_history_scope": "diagnostic_ids_counts_scores_timestamps_only",
    })
    return report["temporal_analysis"]
