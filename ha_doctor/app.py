import json
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from scanner_v031 import scan

PORT = 8099
VERSION = "0.3.1"
DATA_DIR = Path("/data")
REPORT_PATH = DATA_DIR / "report.json"
STATIC_DIR = Path("/app/static")
SCAN_LOCK = threading.Lock()
SCAN_STATE_LOCK = threading.Lock()
SCAN_STATE = {
    "started_at": None,
    "last_completed_at": None,
    "last_error": None,
}


def _include_yaml():
    return os.getenv("HA_DOCTOR_YAML_ANALYSIS", "true").lower() in {"1", "true", "yes", "on"}


def _iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def scan_status():
    with SCAN_STATE_LOCK:
        state = dict(SCAN_STATE)
    state.update({
        "scanning": SCAN_LOCK.locked(),
        "version": VERSION,
        "report_available": REPORT_PATH.exists(),
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
        return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except Exception:
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

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/", ""}:
            html = (STATIC_DIR / "index.html").read_bytes()
            return self._bytes(html, "text/html; charset=utf-8")
        if path.endswith("/api/status") or path == "/api/status":
            return self._json(scan_status())
        if path.endswith("/api/report") or path == "/api/report":
            report = load_report()
            if report is None:
                return self._json({"ready": False}, HTTPStatus.NOT_FOUND)
            return self._json(report)
        if path.endswith("/api/download") or path == "/api/download":
            if not REPORT_PATH.exists():
                return self._json({"error": "Aucun rapport disponible"}, HTTPStatus.NOT_FOUND)
            data = REPORT_PATH.read_bytes()
            return self._bytes(
                data,
                "application/json; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="ha-doctor-report.json"'},
            )
        if path.endswith("/health") or path == "/health":
            return self._json({"status": "ok", "version": VERSION})
        return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = urlparse(self.path).path
        if path.endswith("/api/scan") or path == "/api/scan":
            if SCAN_LOCK.locked():
                return self._json({
                    "error": "Une analyse est déjà en cours",
                    **scan_status(),
                }, HTTPStatus.CONFLICT)
            try:
                report = run_scan()
                return self._json(report)
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
