"""HA Doctor 0.8 scanner entrypoint."""

import scanner_v050_calibration as base
from intelligence_v080 import enrich_v080

VERSION = "0.8.0"


def scan(include_yaml=True):
    report = base.scan(include_yaml=include_yaml)
    report = enrich_v080(report)
    report["version"] = VERSION
    return report
