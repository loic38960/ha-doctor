"""HA Doctor 0.8.8 scanner compatibility entrypoint."""
import time

import scanner_v087 as base
from intelligence_v088 import enrich_v088

VERSION = "0.8.8"
REPORT_SCHEMA = "ha-doctor-report/0.8.8"


def scan(include_yaml=True):
    started = time.monotonic()
    report = base.scan(include_yaml=include_yaml)
    report = enrich_v088(report)
    report["version"] = VERSION
    report["scan_duration_seconds"] = round(time.monotonic() - started, 3)
    return report
