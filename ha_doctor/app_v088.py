"""HA Doctor 0.8.8 control-intelligence runtime wrapper."""
import json
import os
import threading
from urllib.parse import urlparse

import app_v087 as previous
from scanner_v088 import scan as scan_v088
from sharing_v088 import build_share_report

VERSION = "0.8.8"
REPORT_SCHEMA = "ha-doctor-report/0.8.8"

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v088

_original_enhance = previous.enhance_ui_v087

UI_PATCH_V088 = r"""
(function(){
  const renderOverviewLegacy088=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy088(r);
    const s=r.condition_semantics||{},res=r.resilience_analysis||{};
    const target=$('#view-overview');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Control Intelligence 0.8.8</h2><p>Les conflits sont désormais recroisés avec les modes exclusifs, interlocks correctifs et arbitrages par helper.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${s.semantic_v6_resolved_pair_count||0}</div><div class="muted">paire(s) supplémentaire(s) expliquée(s) par V6</div></div>
        <div class="miniCard"><div class="miniBig">${s.physical_unproven_pair_count||0}</div><div class="muted">paire(s) physique(s) restant réellement à revoir</div></div>
        <div class="miniCard"><div class="miniBig">${res.protected_count||0}</div><div class="muted">dépendance(s) externe(s) protégée(s) côté contrôle physique</div></div>
      </div>`);
  };

  const renderQualityLegacy088=renderQuality;
  renderQuality=function(r){
    renderQualityLegacy088(r);
    const s=r.condition_semantics||{},res=r.resilience_analysis||{};
    const target=$('#view-quality');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Calibration 0.8.8</h2><p>La résilience sépare maintenant contrôle physique, helpers et usages observationnels avant de signaler un SPOF.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${(s.supervisory_interlock_pair_count||0)+(s.mediated_interlock_pair_count||0)}</div><div class="muted">interlock(s) direct(s) ou médié(s) reconnus</div></div>
        <div class="miniCard"><div class="miniBig">${res.unprotected_automation_count||0}</div><div class="muted">contrôle(s) physique(s) encore non protégé(s)</div></div>
        <div class="miniCard"><div class="miniBig">${res.observational_consumer_count||0}</div><div class="muted">usage(s) observationnel(s) suivis sans gonfler le risque physique</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v088(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str):
        return enhanced
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "Control Intelligence 0.8.8" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V088 + "\n" + marker, 1)
    return enhanced


_runtime.enhance_ui_v080 = enhance_ui_v088


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path

        if path.endswith("/api/control-intelligence") or path == "/api/control-intelligence":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "version": VERSION,
                "condition_semantics": report.get("condition_semantics") or {},
                "controller_review_summary": report.get("controller_review_summary") or {},
                "resilience_analysis": report.get("resilience_analysis") or {},
                "resilience_recommendations": report.get("resilience_recommendations") or {},
                "quality_gates": report.get("quality_gates") or {},
                "consistency_analysis": report.get("consistency_analysis") or {},
            })

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
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
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
