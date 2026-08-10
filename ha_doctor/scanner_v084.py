"""HA Doctor 0.8.4 scanner entrypoint."""
import time

import scanner_v083 as base
import intelligence_v084

VERSION = "0.8.4"


def scan(include_yaml=True):
    started = time.monotonic()
    report = base.scan(include_yaml=include_yaml)
    report = intelligence_v084.enrich_v084(report)
    report["version"] = VERSION
    report["scan_duration_seconds"] = round(time.monotonic() - started, 3)
    return report
