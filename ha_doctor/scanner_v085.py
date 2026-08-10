"""HA Doctor 0.8.5 scanner entrypoint."""
import time

import scanner_v084 as base
import intelligence_v085_fixed as intelligence

VERSION = "0.8.5"


def scan(include_yaml=True):
    started = time.monotonic()
    report = base.scan(include_yaml=include_yaml)
    report = intelligence.enrich_v085(report)
    report["version"] = VERSION
    report["scan_duration_seconds"] = round(time.monotonic() - started, 3)
    return report
