"""HA Doctor 0.8 runtime wrapper.

Keeps the stable 0.7 HTTP surface while injecting the 0.8 scanner and exposing
flow/coverage endpoints. No write endpoint to Home Assistant is introduced.
"""

import os
import threading
from urllib.parse import urlparse

import app as legacy
from scanner_v080 import scan as scan_v080

VERSION = "0.8.0"
REPORT_SCHEMA = "ha-doctor-report/0.8"

# Reuse the proven runtime, locks, report persistence and download endpoints.
legacy.VERSION = VERSION
legacy.scan = scan_v080

_original_compact_report = legacy.compact_report
_original_insights_report = legacy.insights_report
_original_history_summary = legacy.history_summary


def compact_report_v080(report):
    payload = _original_compact_report(report)
    if not isinstance(payload, dict):
        return payload
    for key in ("automation_coverage", "dependency_graph_meta"):
        if key in report:
            payload[key] = report[key]
    return payload


def insights_report_v080(report):
    payload = _original_insights_report(report)
    if not isinstance(payload, dict):
        return payload
    payload["automation_coverage"] = report.get("automation_coverage") or {}
    payload["dependency_graph_meta"] = report.get("dependency_graph_meta") or {}
    return payload


def history_summary_v080():
    payload = _original_history_summary()
    for source, item in zip(legacy.load_history(legacy.HISTORY_PATH), payload.get("items") or []):
        item["flow_target_resolution_rate"] = source.get("flow_target_resolution_rate")
        item["flow_dynamic_resolution_rate"] = source.get("flow_dynamic_resolution_rate")
        item["automation_coverage_ratio"] = source.get("automation_coverage_ratio")
        item["report_version"] = source.get("report_version")
    payload["version"] = VERSION
    return payload


legacy.compact_report = compact_report_v080
legacy.insights_report = insights_report_v080
legacy.history_summary = history_summary_v080


class Handler(legacy.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path

        if path.endswith("/api/version") or path == "/api/version":
            return self._json({
                "product": "HA Doctor",
                "version": VERSION,
                "report_schema": REPORT_SCHEMA,
                "read_only": True,
                "automatic_fix": False,
                "flow_model": "entity_flow_v3",
            })

        if path.endswith("/api/flow") or path == "/api/flow":
            report = self._report_or_404()
            if report is None:
                return
            graph = report.get("dependency_graph") or []
            unresolved = []
            for node in graph:
                issues = node.get("unresolved_dynamic_targets") or []
                if not issues:
                    continue
                unresolved.append({
                    "automation": node.get("automation"),
                    "source": node.get("source"),
                    "count": len(issues),
                    "targets": issues[:6],
                })
            return self._json({
                "dependency_graph_meta": report.get("dependency_graph_meta") or {},
                "automation_coverage": report.get("automation_coverage") or {},
                "architecture_summary": {
                    key: (report.get("architecture_analysis") or {}).get(key)
                    for key in (
                        "model",
                        "complexity_score",
                        "complexity_label",
                        "shared_actuator_count",
                        "critical_dependency_count",
                        "call_hub_count",
                        "closed_loop_count",
                    )
                },
                "unresolved_dynamic_targets": unresolved[:30],
                "privacy": {
                    "raw_yaml_included": False,
                    "template_text_included": False,
                    "secret_values_included": False,
                },
            })

        if path.endswith("/api/coverage") or path == "/api/coverage":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "automation_coverage": report.get("automation_coverage") or {},
                "maintenance_debt": report.get("maintenance_debt") or {},
            })

        return super().do_GET()


if __name__ == "__main__":
    print(f"[HA Doctor] process started ({VERSION})", flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START", "true").lower() in {"1", "true", "yes", "on"}:
        def initial_scan():
            try:
                legacy.run_scan()
                print("[HA Doctor] initial scan complete", flush=True)
            except Exception as exc:
                print(
                    f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )

        threading.Thread(target=initial_scan, daemon=True).start()

    print(f"[HA Doctor] web server listening on {legacy.PORT}", flush=True)
    legacy.ThreadingHTTPServer(("0.0.0.0", legacy.PORT), Handler).serve_forever()
