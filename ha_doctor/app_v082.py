"""HA Doctor 0.8.2 runtime wrapper.

Reuses the stable 0.8.1 HTTP/UI wrapper and swaps in the calibrated 0.8.2
scanner. The primary Score V4 remains unchanged; contextual scoring is exposed
as a preview only.
"""

import os
import threading

import app_v081 as hardened
from scanner_v082 import scan as scan_v082

VERSION = "0.8.2"
REPORT_SCHEMA = "ha-doctor-report/0.8.2"

hardened.VERSION = VERSION
hardened.REPORT_SCHEMA = REPORT_SCHEMA
hardened.runtime.VERSION = VERSION
hardened.runtime.REPORT_SCHEMA = REPORT_SCHEMA
hardened.runtime.legacy.VERSION = VERSION
hardened.runtime.legacy.scan = scan_v082

_original_compact = hardened.runtime.legacy.compact_report
_original_insights = hardened.runtime.legacy.insights_report


def compact_report_v082(report):
    payload = _original_compact(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "contextual_score_preview",
        "flow_confidence",
        "condition_semantics",
        "resilience_analysis",
        "root_cause_summary",
    ):
        payload[key] = report.get(key) or {}
    return payload


def insights_report_v082(report):
    payload = _original_insights(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "contextual_score_preview",
        "flow_confidence",
        "condition_semantics",
        "resilience_analysis",
        "root_cause_summary",
        "quality_gates",
    ):
        payload[key] = report.get(key) or {}
    return payload


hardened.runtime.legacy.compact_report = compact_report_v082
hardened.runtime.legacy.insights_report = insights_report_v082


class Handler(hardened.Handler):
    server_version = f"HADoctor/{VERSION}"


if __name__ == "__main__":
    print(f"[HA Doctor] process started ({VERSION})", flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START", "true").lower() in {"1", "true", "yes", "on"}:
        def initial_scan():
            try:
                hardened.runtime.legacy.run_scan()
                print("[HA Doctor] initial scan complete", flush=True)
            except Exception as exc:
                print(
                    f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )

        threading.Thread(target=initial_scan, daemon=True).start()

    print(f"[HA Doctor] web server listening on {hardened.runtime.legacy.PORT}", flush=True)
    hardened.runtime.legacy.ThreadingHTTPServer(
        ("0.0.0.0", hardened.runtime.legacy.PORT), Handler
    ).serve_forever()
