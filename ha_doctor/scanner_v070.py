"""HA Doctor 0.7 scanner entrypoint."""

import scanner_v050_calibration as base
from intelligence_v070 import enrich_v070

VERSION = "0.7.0"


def scan(include_yaml=True):
    report = base.scan(include_yaml=include_yaml)
    report = enrich_v070(report)
    report["version"] = VERSION
    return report
