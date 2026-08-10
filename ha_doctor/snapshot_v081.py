"""HA Doctor 0.8.1 single-state-snapshot reconciliation."""
from collections import defaultdict

import scanner_patch as v030
import scanner_v031 as v031

VERSION = "0.8.1"


def synchronize_state_snapshot(report, states):
    """Rebuild every state-derived count from one ephemeral in-memory snapshot."""
    if not isinstance(states, list):
        states = []
    inventory = report.setdefault("inventory", {})
    domains = defaultdict(int)
    unavailable, unknown = [], []
    for item in states:
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entity_id") or "")
        state = item.get("state")
        if "." in entity_id:
            domains[entity_id.split(".", 1)[0]] += 1
        if state == "unavailable":
            unavailable.append(entity_id)
        elif state == "unknown":
            unknown.append(entity_id)
    inventory.update({
        "states": len(states),
        "domains": dict(sorted(domains.items())),
        "unavailable_count": len(unavailable),
        "unknown_count": len(unknown),
        "unavailable_examples": unavailable[:20],
        "unknown_examples": unknown[:20],
    })

    stateless = v030.STATELESS_UNKNOWN_DOMAINS
    had_notify = "notify" in stateless
    stateless.add("notify")
    try:
        health = v030._entity_health(states)
    finally:
        if not had_notify:
            stateless.discard("notify")
    health = v031._refine_entity_health(health)
    report["entity_health"] = health
    v031._sync_entity_finding_summaries(report)

    matches = (
        len(unavailable) == int((health.get("unavailable") or {}).get("total", -1))
        and len(unknown) == int((health.get("unknown") or {}).get("total", -1))
    )
    result = {
        "available": True,
        "model": "single_state_snapshot_v1",
        "state_count": len(states),
        "unavailable_count": len(unavailable),
        "unknown_count": len(unknown),
        "inventory_matches_entity_health": matches,
        "raw_states_persisted": False,
    }
    report["scan_consistency"] = result
    report.setdefault("privacy", {}).update({
        "state_snapshot_ephemeral_cache": True,
        "state_snapshot_persisted": False,
    })
    return result
