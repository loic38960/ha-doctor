"""HA Doctor 0.8.4 temporal V3.1.

Separates final action-plan history from all detected diagnostics and distinguishes
real resolution from contextual de-escalation/removal from the plan.
"""
from datetime import datetime, timezone

import temporal_v083 as base
from temporal_v060 import HISTORY_LIMIT, load_history, save_history

VERSION = "0.8.4"
MODEL = "temporal_v3.1_plan_and_diagnostics"
DEFAULT_MIN_INTERVAL_SECONDS = base.DEFAULT_MIN_INTERVAL_SECONDS


def _history_ids(snapshot, key, fallback=None):
    values = snapshot.get(key)
    if values is None and fallback:
        values = snapshot.get(fallback)
    return {str(x) for x in values or [] if x}


def _seen_with_id(history, diagnostic_id):
    seen = []
    for snap in history:
        ids = _history_ids(snap, "all_diagnostic_ids", fallback="active_ids")
        if diagnostic_id in ids:
            ts = base._parse_ts(snap.get("generated_at"))
            if ts:
                seen.append((ts, snap))
    seen.sort(key=lambda item: item[0])
    return seen


def _previous_qualified_ts(seen, current_ts, min_interval):
    if not current_ts:
        return None
    candidates = [ts for ts, _ in seen if (current_ts - ts).total_seconds() >= min_interval]
    return max(candidates) if candidates else None


def _status_for(item, history, current_ts, min_interval, in_plan):
    diagnostic_id = str(item.get("id") or "")
    seen = _seen_with_id(history, diagnostic_id)
    first_ts = seen[0][0] if seen else current_ts
    last_raw_ts = seen[-1][0] if seen else None
    previous_qualified_ts = _previous_qualified_ts(seen, current_ts, min_interval)
    age = base._seconds(current_ts, first_ts)
    raw_gap = base._seconds(current_ts, last_raw_ts)
    qualified_gap = base._seconds(current_ts, previous_qualified_ts)
    qualified = base._qualified_observations(seen, current_ts, min_interval)

    previous_all = _history_ids(history[-1], "all_diagnostic_ids", fallback="active_ids") if history else set()
    seen_before = bool(seen)
    previously_seen_raw = diagnostic_id in previous_all

    if not history:
        status = "baseline"
    elif not seen_before:
        status = "new" if in_plan else "observed_not_plan_tracked"
    elif previously_seen_raw:
        if age is not None and age >= min_interval and len(qualified) >= 2:
            status = "persistent"
        else:
            status = "new" if in_plan else "observed_not_plan_tracked"
    else:
        status = "recurrent"

    source_type = str(item.get("source_type") or "")
    if source_type.startswith("registry_"):
        factor = {"baseline": 0.72, "new": 0.72, "observed_not_plan_tracked": 0.72, "recurrent": 0.86, "persistent": 1.0}.get(status, 0.82)
    else:
        factor = {"baseline": 0.94, "new": 0.94, "observed_not_plan_tracked": 0.94, "recurrent": 0.97, "persistent": 1.0}.get(status, 1.0)

    raw_is_rapid = bool(raw_gap is not None and raw_gap < min_interval)
    previous_observation_qualified = bool(last_raw_ts is not None and previous_qualified_ts == last_raw_ts)
    rapid_previous_ignored = bool(raw_is_rapid and not previous_observation_qualified)

    return {
        "status": status,
        "scope": "action_plan" if in_plan else "diagnostic_observation",
        "occurrences": len(seen) + 1,
        "qualified_observations": len(qualified),
        "first_seen": first_ts.isoformat().replace("+00:00", "Z") if first_ts else None,
        "last_seen_before_current": last_raw_ts.isoformat().replace("+00:00", "Z") if last_raw_ts else None,
        "age_seconds": int(age) if age is not None else None,
        "previous_raw_scan_gap_seconds": int(raw_gap) if raw_gap is not None else None,
        "previous_qualified_scan_gap_seconds": int(qualified_gap) if qualified_gap is not None else None,
        "previous_observation_qualified": previous_observation_qualified,
        "rapid_previous_scan_ignored_for_persistence": rapid_previous_ignored,
        "seconds_since_previous_observation": int(raw_gap) if raw_gap is not None else None,
        "minimum_persistence_interval_seconds": min_interval,
        "rapid_rescan_ignored": rapid_previous_ignored,
        "persistence_factor": factor,
        "model": MODEL,
    }


def apply_temporal_v31(report, history_path="/data/ha-doctor-history.json", min_interval_seconds=DEFAULT_MIN_INTERVAL_SECONDS):
    full_history = load_history(history_path)
    current_generated_at = str(report.get("generated_at") or "")
    history = [snap for snap in full_history if str(snap.get("generated_at") or "") != current_generated_at]
    current_ts = base._parse_ts(report.get("generated_at")) or datetime.now(timezone.utc)

    plan_items = (report.get("action_plan") or {}).get("items") or []
    current_plan_ids = {str(item.get("id") or "") for item in plan_items if item.get("id")}
    explanations = report.get("diagnostic_explanations") or []
    current_all_ids = {str(item.get("id") or "") for item in explanations if item.get("id")}

    by_id = {}
    for item in explanations:
        diagnostic_id = str(item.get("id") or "")
        temporal = _status_for(item, history, current_ts, min_interval_seconds, diagnostic_id in current_plan_ids)
        item["temporal"] = temporal
        if diagnostic_id:
            by_id[diagnostic_id] = temporal

    for section_name in ("action_plan", "recommendation_queue"):
        section = report.get(section_name) or {}
        for item in section.get("items") or []:
            diagnostic_id = str(item.get("id") or "")
            if diagnostic_id in by_id:
                item["temporal"] = dict(by_id[diagnostic_id])
        if section_name == "action_plan":
            section["top"] = list((section.get("items") or [])[:6])

    previous = base._meaningful_previous(history, current_ts, min_interval_seconds)
    previous_plan_ids = _history_ids(previous, "active_ids") if previous else set()
    left_plan = previous_plan_ids - current_plan_ids
    still_detected = left_plan & current_all_ids
    truly_resolved = left_plan - current_all_ids

    new_ids = sorted(diagnostic_id for diagnostic_id in current_plan_ids if (by_id.get(diagnostic_id) or {}).get("status") == "new")
    persistent_ids = sorted(diagnostic_id for diagnostic_id in current_plan_ids if (by_id.get(diagnostic_id) or {}).get("status") == "persistent")
    recurrent_ids = sorted(diagnostic_id for diagnostic_id in current_plan_ids if (by_id.get(diagnostic_id) or {}).get("status") == "recurrent")

    report["temporal_analysis"] = {
        **(report.get("temporal_analysis") or {}),
        "enabled": True,
        "model": MODEL,
        "history_limit": HISTORY_LIMIT,
        "minimum_persistence_interval_seconds": min_interval_seconds,
        "meaningful_previous_generated_at": previous.get("generated_at") if previous else None,
        "new_count": len(new_ids),
        "persistent_count": len(persistent_ids),
        "recurrent_count": len(recurrent_ids),
        "resolved_since_previous_count": len(truly_resolved),
        "deescalated_since_previous_count": len(still_detected),
        "new_ids": new_ids[:20],
        "persistent_ids": persistent_ids[:20],
        "recurrent_ids": recurrent_ids[:20],
        "resolved_since_previous": sorted(truly_resolved)[:20],
        "deescalated_since_previous": sorted(still_detected)[:20],
        "still_detected_outside_plan": sorted(current_all_ids - current_plan_ids)[:30],
        "all_diagnostic_count": len(current_all_ids),
        "action_plan_diagnostic_count": len(current_plan_ids),
        "rapid_rescan_protection": True,
        "rapid_rescans_promote_persistence": False,
        "scope": "action_plan_plus_all_diagnostics",
        "presentation_note": (
            "resolved signifie désormais absent du plan ET absent des diagnostics. Un diagnostic "
            "encore détecté mais déclassé est marqué deescalated."
        ),
        "note": (
            "Temporal V3.1 conserve deux historiques compacts : plan d'action et diagnostics "
            "observés. Aucun état brut n'est stocké."
        ),
    }

    history_now = load_history(history_path)
    if history_now and str(history_now[-1].get("generated_at") or "") == current_generated_at:
        snap = dict(history_now[-1])
        snap.update({
            "report_version": VERSION,
            "temporal_model": MODEL,
            "active_ids": sorted(current_plan_ids),
            "all_diagnostic_ids": sorted(current_all_ids),
            "deescalated_ids": sorted(current_all_ids - current_plan_ids),
            "minimum_persistence_interval_seconds": min_interval_seconds,
            "qualified_new_count": len(new_ids),
            "qualified_persistent_count": len(persistent_ids),
            "qualified_recurrent_count": len(recurrent_ids),
        })
        history_now[-1] = snap
        save_history(history_now, history_path)

    report.setdefault("privacy", {}).update({
        "temporal_history_raw_states_persisted": False,
        "temporal_history_secret_values_persisted": False,
        "temporal_history_scope": "action_plan_ids_all_diagnostic_ids_counts_scores_timestamps_only",
    })
    return report["temporal_analysis"]
