import json
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scanner_v070 import scan
from share_export import build_anonymized_report
from temporal_v060 import load_history

PORT = 8099
VERSION = "0.7.0"
DATA_DIR = Path("/data")
REPORT_PATH = DATA_DIR / "report.json"
HISTORY_PATH = DATA_DIR / "ha-doctor-history.json"
STATIC_DIR = Path("/app/static")
SCAN_LOCK = threading.Lock()
SCAN_STATE_LOCK = threading.Lock()
SCAN_STATE = {"started_at": None, "last_completed_at": None, "last_error": None}


def _include_yaml():
    return os.getenv("HA_DOCTOR_YAML_ANALYSIS", "true").lower() in {"1", "true", "yes", "on"}


def _iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _history_score(item):
    if not isinstance(item, dict):
        return None
    score = item.get("health_score_v4")
    if score is None:
        score = item.get("health_score_v3")
    return score


def scan_status():
    with SCAN_STATE_LOCK:
        state = dict(SCAN_STATE)
    state.update({
        "scanning": SCAN_LOCK.locked(),
        "version": VERSION,
        "report_available": REPORT_PATH.exists(),
        "history_available": HISTORY_PATH.exists(),
        "history_count": len(load_history(HISTORY_PATH)),
        "read_only": True,
        "automatic_fix": False,
    })
    return state


def run_scan():
    with SCAN_LOCK:
        with SCAN_STATE_LOCK:
            SCAN_STATE["started_at"] = _iso_now()
            SCAN_STATE["last_error"] = None
        print("[HA Doctor] analysis started", flush=True)
        try:
            report = scan(include_yaml=_include_yaml())
            report["version"] = VERSION
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = REPORT_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(REPORT_PATH)
            with SCAN_STATE_LOCK:
                SCAN_STATE["last_completed_at"] = _iso_now()
            print("[HA Doctor] analysis complete", flush=True)
            return report
        except Exception as exc:
            with SCAN_STATE_LOCK:
                SCAN_STATE["last_error"] = type(exc).__name__
            raise
        finally:
            with SCAN_STATE_LOCK:
                SCAN_STATE["started_at"] = None


def load_report():
    if not REPORT_PATH.exists():
        return None
    try:
        data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def compact_report(report):
    """Smaller diagnostic report. Compact does not mean anonymous."""
    if not isinstance(report, dict):
        return None
    compact = {}
    for key in (
        "product", "version", "generated_at", "scan_duration_seconds", "privacy",
        "scores", "score_meta", "diagnostic_engine", "executive_summary",
        "diagnostic_summary", "action_plan", "registry_observations",
        "root_cause_summary", "temporal_analysis", "regression_analysis",
        "architecture_analysis", "maintenance_debt", "quality_gates",
        "recommendation_queue", "dependency_graph_meta", "report_schema",
    ):
        if key in report:
            compact[key] = report[key]

    inventory = report.get("inventory") or {}
    compact["inventory_summary"] = {
        "states": inventory.get("states"),
        "automations_detected": inventory.get("automations_detected"),
        "blueprints_detected": inventory.get("blueprints_detected"),
        "yaml_files_scanned": inventory.get("yaml_files_scanned"),
        "unavailable_count": inventory.get("unavailable_count"),
        "unknown_count": inventory.get("unknown_count"),
    }

    registry = report.get("registry_analysis") or {}
    if registry:
        integration = registry.get("integration_health") or {}
        devices = registry.get("device_health") or {}
        orphan = registry.get("orphan_analysis") or {}
        compact["registry_summary"] = {
            "available": registry.get("available"),
            "entity_registry_count": registry.get("entity_registry_count"),
            "device_registry_count": registry.get("device_registry_count"),
            "integration_health": {
                "total": integration.get("total"),
                "affected": integration.get("affected"),
                "problematic": integration.get("problematic"),
                "offline": integration.get("offline"),
                "groups": [
                    item for item in (integration.get("groups") or [])
                    if item.get("status") in {"offline", "degraded", "watch"}
                ][:20],
            },
            "device_health": {
                "total": devices.get("total"),
                "affected": devices.get("affected"),
                "problematic": devices.get("problematic"),
                "offline": devices.get("offline"),
                "groups": [
                    item for item in (devices.get("groups") or [])
                    if item.get("status") in {"offline", "degraded", "watch"}
                ][:20],
            },
            "orphan_analysis": {
                "probable_orphan_count": orphan.get("probable_orphan_count", orphan.get("high_confidence_count", 0)),
                "review_candidate_count": orphan.get("review_candidate_count", 0),
                "probable_orphans": (orphan.get("probable_orphans") or [])[:20],
                "local_unavailable_candidates": (orphan.get("local_unavailable_candidates") or [])[:20],
            },
            "errors": registry.get("errors") or [],
        }

    compact["export_meta"] = {
        "type": "diagnostic_summary",
        "full_dependency_graph_included": False,
        "raw_states_included": False,
        "identifiers_removed": False,
        "intended_for_sharing": True,
        "note": "Ce résumé est compact mais pas anonymisé. Utiliser l'export anonymisé pour un partage public.",
    }
    return compact


def history_summary():
    history = load_history(HISTORY_PATH)
    return {
        "version": VERSION,
        "count": len(history),
        "limit": 20,
        "items": [
            {
                "generated_at": x.get("generated_at"),
                "health_score": _history_score(x),
                "health_score_v4": x.get("health_score_v4"),
                "health_score_v3": x.get("health_score_v3"),
                "legacy_score": x.get("legacy_score"),
                "priority_counts": x.get("priority_counts"),
                "unavailable_count": x.get("unavailable_count"),
                "unknown_count": x.get("unknown_count"),
                "active_diagnostic_count": len(x.get("active_ids") or []),
                "registry_incident_count": len(x.get("registry_ids") or []),
                "architecture": x.get("architecture"),
                "maintenance_debt_score": x.get("maintenance_debt_score"),
            }
            for x in history
        ],
        "privacy": {
            "raw_states_included": False,
            "secret_values_included": False,
            "diagnostic_ids_exposed": False,
        },
    }


def insights_report(report):
    if not isinstance(report, dict):
        return None
    return {
        "product": report.get("product"),
        "version": report.get("version"),
        "generated_at": report.get("generated_at"),
        "scores": report.get("scores"),
        "executive_summary": report.get("executive_summary"),
        "diagnostic_summary": report.get("diagnostic_summary"),
        "regression_analysis": report.get("regression_analysis"),
        "root_cause_summary": report.get("root_cause_summary"),
        "architecture_analysis": report.get("architecture_analysis"),
        "maintenance_debt": report.get("maintenance_debt"),
        "quality_gates": report.get("quality_gates"),
        "recommendation_queue": report.get("recommendation_queue"),
        "report_schema": report.get("report_schema"),
    }


def diagnostic_detail(report, diagnostic_id):
    if not isinstance(report, dict) or not diagnostic_id:
        return None
    for item in report.get("diagnostic_explanations") or []:
        if str(item.get("id") or "") == diagnostic_id:
            return item
    for item in (report.get("action_plan") or {}).get("items") or []:
        if str(item.get("id") or "") == diagnostic_id:
            return item
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = f"HADoctor/{VERSION}"

    def log_message(self, fmt, *args):
        print(f"[HA Doctor] {self.address_string()} - {fmt % args}", flush=True)

    def _json(self, payload, status=200, headers=None):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _bytes(self, data, content_type, status=200, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _report_or_404(self):
        report = load_report()
        if report is None:
            self._json({"ready": False, "error": "Aucun rapport disponible"}, HTTPStatus.NOT_FOUND)
            return None
        return report

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in {"/", ""}:
            html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
            html = html.replace("__HA_DOCTOR_VERSION__", VERSION)
            return self._bytes(html.encode("utf-8"), "text/html; charset=utf-8")
        if path.endswith("/api/status") or path == "/api/status":
            return self._json(scan_status())
        if path.endswith("/api/version") or path == "/api/version":
            return self._json({"product": "HA Doctor", "version": VERSION, "report_schema": "ha-doctor-report/0.7", "read_only": True})
        if path.endswith("/api/report") or path == "/api/report":
            report = load_report()
            return self._json(report if report is not None else {"ready": False}, 200 if report is not None else HTTPStatus.NOT_FOUND)
        if path.endswith("/api/history") or path == "/api/history":
            return self._json(history_summary())
        if path.endswith("/api/summary") or path == "/api/summary":
            report = self._report_or_404()
            if report is None:
                return
            return self._json(compact_report(report))
        if path.endswith("/api/insights") or path == "/api/insights":
            report = self._report_or_404()
            if report is None:
                return
            return self._json(insights_report(report))
        if path.endswith("/api/actions") or path == "/api/actions":
            report = self._report_or_404()
            if report is None:
                return
            return self._json(report.get("action_plan") or {})
        if path.endswith("/api/architecture") or path == "/api/architecture":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "architecture_analysis": report.get("architecture_analysis") or {},
                "dependency_graph_meta": report.get("dependency_graph_meta") or {},
            })
        if path.endswith("/api/quality") or path == "/api/quality":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "quality_gates": report.get("quality_gates") or {},
                "maintenance_debt": report.get("maintenance_debt") or {},
                "privacy": report.get("privacy") or {},
            })
        if path.endswith("/api/diagnostic") or path == "/api/diagnostic":
            report = self._report_or_404()
            if report is None:
                return
            diagnostic_id = str((query.get("id") or [""])[0])
            item = diagnostic_detail(report, diagnostic_id)
            if item is None:
                return self._json({"error": "Diagnostic introuvable", "id": diagnostic_id}, HTTPStatus.NOT_FOUND)
            return self._json(item)
        if path.endswith("/api/download-summary") or path == "/api/download-summary":
            report = self._report_or_404()
            if report is None:
                return
            data = json.dumps(compact_report(report), ensure_ascii=False, indent=2).encode("utf-8")
            return self._bytes(data, "application/json; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ha-doctor-summary.json"'})
        if path.endswith("/api/download-anonymized") or path == "/api/download-anonymized":
            report = self._report_or_404()
            if report is None:
                return
            data = json.dumps(build_anonymized_report(report), ensure_ascii=False, indent=2).encode("utf-8")
            return self._bytes(data, "application/json; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ha-doctor-anonymized.json"'})
        if path.endswith("/api/download") or path == "/api/download":
            if not REPORT_PATH.exists():
                return self._json({"error": "Aucun rapport disponible"}, HTTPStatus.NOT_FOUND)
            return self._bytes(REPORT_PATH.read_bytes(), "application/json; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ha-doctor-report.json"'})
        if path.endswith("/health") or path == "/health":
            return self._json({"status": "ok", "version": VERSION, "read_only": True, "report_available": REPORT_PATH.exists()})
        return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = urlparse(self.path).path
        if path.endswith("/api/scan") or path == "/api/scan":
            if SCAN_LOCK.locked():
                return self._json({"error": "Une analyse est déjà en cours", **scan_status()}, HTTPStatus.CONFLICT)
            try:
                return self._json(run_scan())
            except Exception as exc:
                print(f"[HA Doctor] scan failed: {type(exc).__name__}: {exc}", flush=True)
                return self._json({"error": "Le scan a échoué", "type": type(exc).__name__}, HTTPStatus.INTERNAL_SERVER_ERROR)
        return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


if __name__ == "__main__":
    print(f"[HA Doctor] process started ({VERSION})", flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START", "true").lower() in {"1", "true", "yes", "on"}:
        def initial_scan():
            try:
                run_scan()
                print("[HA Doctor] initial scan complete", flush=True)
            except Exception as exc:
                print(f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}", flush=True)
        threading.Thread(target=initial_scan, daemon=True).start()
    print(f"[HA Doctor] web server listening on {PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
