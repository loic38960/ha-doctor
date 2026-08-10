"""HA Doctor 0.8.1 runtime wrapper.

Reuses the stable 0.8 HTTP/UI layer and swaps in the hardened 0.8.1 scanner.
"""

import os
import threading
from urllib.parse import urlparse

import app_v080 as runtime
from scanner_v081 import scan as scan_v081

VERSION = "0.8.1"
REPORT_SCHEMA = "ha-doctor-report/0.8.1"

runtime.VERSION = VERSION
runtime.REPORT_SCHEMA = REPORT_SCHEMA
runtime.legacy.VERSION = VERSION
runtime.legacy.scan = scan_v081

_original_compact = runtime.legacy.compact_report
_original_insights = runtime.legacy.insights_report


def compact_report_v081(report):
    payload = _original_compact(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "scan_consistency",
        "flow_confidence",
        "condition_semantics",
        "operational_context",
    ):
        if key in report:
            payload[key] = report[key]
    return payload


def insights_report_v081(report):
    payload = _original_insights(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "scan_consistency",
        "flow_confidence",
        "condition_semantics",
        "call_graph_analysis",
        "operational_context",
        "resilience_analysis",
    ):
        payload[key] = report.get(key) or {}
    return payload


runtime.legacy.compact_report = compact_report_v081
runtime.legacy.insights_report = insights_report_v081


class Handler(runtime.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/hardening") or path == "/api/hardening":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "scan_consistency": report.get("scan_consistency") or {},
                "flow_confidence": report.get("flow_confidence") or {},
                "condition_semantics": report.get("condition_semantics") or {},
                "call_graph_analysis": report.get("call_graph_analysis") or {},
                "operational_context": report.get("operational_context") or {},
                "resilience_analysis": report.get("resilience_analysis") or {},
                "quality_gates": report.get("quality_gates") or {},
            })
        return super().do_GET()


if __name__ == "__main__":
    print(f"[HA Doctor] process started ({VERSION})", flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START", "true").lower() in {"1", "true", "yes", "on"}:
        def initial_scan():
            try:
                runtime.legacy.run_scan()
                print("[HA Doctor] initial scan complete", flush=True)
            except Exception as exc:
                print(
                    f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )

        threading.Thread(target=initial_scan, daemon=True).start()

    print(f"[HA Doctor] web server listening on {runtime.legacy.PORT}", flush=True)
    runtime.legacy.ThreadingHTTPServer(("0.0.0.0", runtime.legacy.PORT), Handler).serve_forever()
