"""HA Doctor 0.8.6 share-report runtime wrapper."""
import json
import os
import threading
from urllib.parse import urlparse

import app_v085 as previous
from scanner_v086 import scan as scan_v086
from sharing_v086 import build_share_report

VERSION = "0.8.6"
REPORT_SCHEMA = "ha-doctor-report/0.8.6"

# Propagate the runtime version through the wrapper stack and replace the final
# scanner entrypoint. The diagnostic models remain those validated in 0.8.5;
# 0.8.6 changes how a bounded report can be shared, not how HA is modified.
previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.VERSION = VERSION
previous.previous.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.VERSION = VERSION
previous.previous.previous.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.calibrated.VERSION = VERSION
previous.previous.previous.calibrated.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.calibrated.hardened.VERSION = VERSION
previous.previous.previous.calibrated.hardened.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.calibrated.hardened.runtime.VERSION = VERSION
previous.previous.previous.calibrated.hardened.runtime.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.previous.calibrated.hardened.runtime.legacy.VERSION = VERSION
previous.previous.previous.calibrated.hardened.runtime.legacy.scan = scan_v086

_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v086
_original_enhance = previous.enhance_ui_v085

UI_PATCH_V086 = r"""
(function(){
  const actions=document.querySelector('.actions');
  const full=document.getElementById('downloadBtn');
  if(actions && !document.getElementById('shareBtn')){
    const share=document.createElement('a');
    share.id='shareBtn';
    share.className='btn secondary';
    share.href=api('download-share');
    share.textContent='Rapport à envoyer';
    share.title='Export compact pour ChatGPT ou le support, avec les détails de diagnostic utiles';
    if(full) actions.insertBefore(share,full); else actions.appendChild(share);
  }

  const renderQualityLegacy086=renderQuality;
  renderQuality=function(r){
    renderQualityLegacy086(r);
    const target=$('#view-quality');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Partage 0.8.6</h2><p>Le rapport complet reste local ; l'export à envoyer supprime les gros blocs répétés tout en conservant les diagnostics utiles.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">Compact</div><div class="muted">graphe complet exclu de l'export à envoyer</div></div>
        <div class="miniCard"><div class="miniBig">IDs</div><div class="muted">entity_id conservés pour permettre le diagnostic</div></div>
        <div class="miniCard"><div class="miniBig">0</div><div class="muted">état brut, YAML brut ou valeur de secret ajouté à l'export</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v086(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str):
        return enhanced
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "Partage 0.8.6" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V086 + "\n" + marker, 1)
    return enhanced


previous.previous.previous.calibrated.hardened.runtime.enhance_ui_v080 = enhance_ui_v086


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/share-report") or path == "/api/share-report":
            report = self._report_or_404()
            if report is None:
                return
            payload = build_share_report(report)
            return self._json(payload)

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
            full_bytes = int((payload.get("export_meta") or {}).get("full_report_bytes_estimate", 0) or 0)
            headers = {
                "Content-Disposition": 'attachment; filename="ha-doctor-share.json"',
                "X-HA-Doctor-Share-Bytes": str(len(data)),
                "X-HA-Doctor-Full-Bytes": str(full_bytes),
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
