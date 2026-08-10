"""HA Doctor 0.9 milestone scanner.

0.9 keeps the validated 0.8.8 acquisition/semantic pipeline and adds only pure
post-processing: product triage, report self-check and publication readiness.
No second Home Assistant state request is performed.
"""
import time

import scanner_v088 as base
from finalize_v090 import finalize_release
from product_v090 import apply_product_intelligence
from selfcheck_v090 import run_self_check

VERSION = "0.9.0"
REPORT_SCHEMA = "ha-doctor-report/0.9"


def scan(include_yaml=True):
    started = time.monotonic()
    report = base.scan(include_yaml=include_yaml)
    apply_product_intelligence(report)
    run_self_check(report)
    finalize_release(report)
    report["version"] = VERSION
    report.setdefault("report_schema", {})["version"] = REPORT_SCHEMA
    report.setdefault("privacy", {}).update({
        "v090_additional_home_assistant_state_reads": 0,
        "v090_automatic_configuration_changes": False,
    })
    report["scan_duration_seconds"] = round(time.monotonic() - started, 3)
    return report
