"""HA Doctor 0.3.2 bugfix layer.

Ensures Home Assistant notify entities are treated as stateless before the 0.3
entity-health grouping runs. This fixes mobile notify entities being grouped as
stateful unknowns because their object_id contains iPhone/iPad markers.
"""

import scanner_v031 as v031

VERSION = "0.3.2"


def scan(include_yaml=True):
    domains = v031.v030.STATELESS_UNKNOWN_DOMAINS
    notify_was_present = "notify" in domains
    domains.add("notify")
    try:
        report = v031.scan(include_yaml=include_yaml)
    finally:
        if not notify_was_present:
            domains.discard("notify")

    report["version"] = VERSION
    score_meta = dict(report.get("score_meta") or {})
    score_meta["model"] = "priority_v1.2"
    score_meta["note"] = (
        "Indice de santé alpha : priorités client + triage des entités, avec les entités notify stateless exclues des unknown à examiner."
    )
    report["score_meta"] = score_meta
    return report
