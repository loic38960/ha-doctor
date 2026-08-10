"""HA Doctor 0.8.7 compact assistant handoff runtime wrapper."""
import json
import os
import threading
from urllib.parse import urlparse

import app_v086 as previous
from scanner_v087 import scan as scan_v087
from sharing_v087 import build_share_report

VERSION = "0.8.7"
REPORT_SCHEMA = "ha-doctor-report/0.8.7"

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.VERSION = VERSION
previous.previous.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.VERSION = VERSION
previous.previous.previous.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.previous.VERSION = VERSION
previous.previous.previous.previous.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.previous.calibrated.VERSION = VERSION
previous.previous.previous.previous.calibrated.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.previous.calibrated.hardened.VERSION = VERSION
previous.previous.previous.previous.calibrated.hardened.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.previous.calibrated.hardened.runtime.VERSION = VERSION
previous.previous.previous.previous.calibrated.hardened.runtime.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.previous.calibrated.hardened.runtime.legacy.VERSION = VERSION
previous.previous.previous.previous.calibrated.hardened.runtime.legacy.scan = scan_v087

_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v087
_original_enhance = previous.enhance_ui_v086

UI_PATCH_V087 = r"""
(function(){
  const share=document.getElementById('shareBtn');
  if(share){
    share.textContent='Rapport à envoyer · compact';
    share.href=api('download-share');
    share.title='Export V2 fortement allégé pour ChatGPT ou le support, avec diagnostics et IDs utiles';
  }

  const renderQualityLegacy087=renderQuality;
  renderQuality=function(r){
    renderQualityLegacy087(r);
    const target=$('#view-quality');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Partage 0.8.7</h2><p>Le paquet assistant V2 est plafonné et conserve les diagnostics, IDs, contrôleurs et dépendances utiles sans recopier les gros blocs du rapport local.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">≤36 Ko</div><div class="muted">plafond dur visé pour l'export à envoyer</div></div>
        <div class="miniCard"><div class="miniBig">V2</div><div class="muted">priorités, contrôleurs, registry et résilience conservés</div></div>
        <div class="miniCard"><div class="miniBig">Local</div><div class="muted">le rapport complet reste disponible dans HA Doctor</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v087(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str):
        return enhanced
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "Partage 0.8.7" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V087 + "\n" + marker, 1)
    return enhanced


previous.previous.previous.previous.calibrated.hardened.runtime.enhance_ui_v080 = enhance_ui_v087


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/share-report") or path == "/api/share-report":
            report = self._report_or_404()
            if report is None:
                return
            return self._json(build_share_report(report))

        if path.endswith("/api/download-share") or path == "/api/download-share":
            report = self._report_or_404()
            if report is None:
                return
            payload = build_share_report(report)
            data = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            meta = payload.get("export_meta") or {}
            headers = {
                "Content-Disposition": 'attachment; filename="ha-doctor-share.json"',
                "X-HA-Doctor-Share-Bytes": str(len(data)),
                "X-HA-Doctor-Full-Bytes": str(int(meta.get("full_report_bytes_estimate", 0) or 0)),
                "X-HA-Doctor-Share-Model": "assistant_share_report_v2",
            }
            return self._bytes(data, "application/json; charset=utf-8", headers=headers)

        return super().do_GET()


if __name__ == "__main__":
    print(f"[HA Doctor] process started ({VERSION})", flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START", "true").lower() in {"1", "true", "yes", "on"}:
        def initial_scan():
            try:
                _runtime.run_scan()
                print("[HA Doctor] initial scan complete", flush=True)
            except Exception as exc:
                print(f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}", flush=True)
        threading.Thread(target=initial_scan, daemon=True).start()

    print(f"[HA Doctor] web server listening on {_runtime.PORT}", flush=True)
    _runtime.ThreadingHTTPServer(("0.0.0.0", _runtime.PORT), Handler).serve_forever()
