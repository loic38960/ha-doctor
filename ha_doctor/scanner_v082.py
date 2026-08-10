"""HA Doctor 0.8.2 scanner entrypoint.

Reuses the proven 0.8.1 single-state-snapshot scan, then applies only the
0.8.2 calibration/consistency layer. No additional Home Assistant state read is
performed here.
"""

import scanner_v081 as base
import intelligence_v082

VERSION = "0.8.2"


def scan(include_yaml=True):
    report = base.scan(include_yaml=include_yaml)
    report = intelligence_v082.enrich_v082(report)
    report["version"] = VERSION
    return report
