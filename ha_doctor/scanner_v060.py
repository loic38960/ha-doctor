"""HA Doctor 0.6 root-cause, temporal and dependency-aware scoring layer."""

import scanner_v050_calibration as base
from temporal_v060 import enrich_v060

VERSION = "0.6.1"


def scan(include_yaml=True):
    report = base.scan(include_yaml=include_yaml)
    report = enrich_v060(report)
    report["version"] = VERSION
    return report
