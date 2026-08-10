"""HA Doctor 0.8.7 scanner compatibility entrypoint."""
import time

import scanner_v086 as base
from hardening_v087 import harden_report_v087

VERSION = "0.8.7"
REPORT_SCHEMA = "ha-doctor-report/0.8.7"


def scan(include_yaml=True):
    started = time.monotonic()
    report = base.scan(include_yaml=include_yaml)
    report = harden_report_v087(report)
    report["scan_duration_seconds"] = round(time.monotonic() - started, 3)
    return report
