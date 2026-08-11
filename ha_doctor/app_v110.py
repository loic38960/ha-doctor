"""HA Doctor 0.11 Cross-Validated Engine runtime."""

import json
import os
import threading
from urllib.parse import urlparse

import app_v100 as previous
from contracts_v110 import VERSION, REPORT_SCHEMA, SHARE_SCHEMA
from scanner_v110 import scan as scan_v110
from sharing_v110 import MODEL as SHARE_MODEL, build_markdown_summary, build_share_report

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v110
_original_enhance = previous.enhance_ui_v100

UI_PATCH_V110 = r"""
(function(){
  const renderOverviewLegacy110=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy110(r);
    const p=r.product_intelligence||{},truth=p.cross_section_truth||{},sec=p.security||{},maint=p.maintenance||{},ctrl=p.controller_review_trace||{},res=p.resilience_trace||{};
    const target=$('#view-overview'); if(!target) return;
    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>HA Doctor 0.11 · Cross-Validated Engine</h2><p>Les findings, la vue client et l'export support sont maintenant contrôlés les uns contre les autres.</p></div>${badge((r.self_check||{}).status||'—',(r.self_check||{}).status==='pass'?'pass':'warn')}</div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="card"><div class="muted">Sécurité source</div><div class="miniBig">${sec.active_secret_hint_count??0} / ${sec.archive_secret_hint_count??0}</div><div class="rootText">indices actifs / archives, dérivés directement des findings.</div></div>
        <div class="card"><div class="muted">Maintenance source</div><div class="miniBig">${maint.missing_reference_count??0}</div><div class="rootText">références absentes · ${maint.local_unavailable_review??0} indisponibles locales à revoir.</div></div>
        <div class="card"><div class="muted">Preuve physique</div><div class="miniBig">${ctrl.physical_pair_count??0}</div><div class="rootText">paire(s) à revoir · ${ctrl.numeric_overlap_pair_count??0} overlap(s) numérique(s).</div></div>
      </div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${res.must_fix_count??0}</div><div class="muted">exposition(s) résilience réelle(s)</div></div>
        <div class="miniCard"><div class="miniBig">${res.hardening_count??0}</div><div class="muted">durcissement(s) recommandé(s)</div></div>
        <div class="miniCard"><div class="miniBig">${truth.single_snapshot_evidence?'1':'0'}</div><div class="muted">snapshot HA unique prouvé</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v110(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str):
        return enhanced
    enhanced = enhanced.replace("Le contrôle technique de votre Home Assistant · Engine Candidate", "Le contrôle technique de votre Home Assistant · Cross-Validated Engine")
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "HA Doctor 0.11 · Cross-Validated Engine" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V110 + "\n" + marker, 1)
    return enhanced

_runtime.enhance_ui_v080 = enhance_ui_v110


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/version") or path == "/api/version":
            return self._json({"product":"HA Doctor","version":VERSION,"report_schema":REPORT_SCHEMA,"share_schema":SHARE_SCHEMA,"read_only":True,"automatic_fix":False,"cross_validated_engine":True})
        if path.endswith("/api/evidence") or path == "/api/evidence":
            report = self._report_or_404()
            if report is None: return
            p = report.get("product_intelligence") or {}
            return self._json({"version":VERSION,"cross_section_truth":p.get("cross_section_truth") or {},"controller_review_trace":p.get("controller_review_trace") or {},"resilience_trace":p.get("resilience_trace") or {},"score_change_trace":p.get("score_change_trace") or {}})
        if path.endswith("/api/share-report") or path == "/api/share-report":
            report = self._report_or_404()
            if report is None: return
            return self._json(build_share_report(report))
        if path.endswith("/api/download-share") or path == "/api/download-share":
            report = self._report_or_404()
            if report is None: return
            payload = build_share_report(report)
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            meta = payload.get("export_meta") or {}
            return self._bytes(data,"application/json; charset=utf-8",headers={"Content-Disposition":'attachment; filename="ha-doctor-support.json"',"X-HA-Doctor-Share-Bytes":str(len(data)),"X-HA-Doctor-Share-Model":SHARE_MODEL,"X-HA-Doctor-Export-Validated":"true" if meta.get("within_hard_bytes") else "false"})
        if path.endswith("/api/download-support-summary") or path == "/api/download-support-summary":
            report = self._report_or_404()
            if report is None: return
            return self._bytes(build_markdown_summary(report).encode("utf-8"),"text/markdown; charset=utf-8",headers={"Content-Disposition":'attachment; filename="ha-doctor-summary.md"'})
        return super().do_GET()


if __name__ == "__main__":
    print(f"[HA Doctor] process started ({VERSION})", flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START", "true").lower() in {"1", "true", "yes", "on"}:
        def initial_scan():
            try:
                _runtime.run_scan(); print("[HA Doctor] initial scan complete", flush=True)
            except Exception as exc:
                print(f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}", flush=True)
        threading.Thread(target=initial_scan, daemon=True).start()
    print(f"[HA Doctor] web server listening on {_runtime.PORT}", flush=True)
    _runtime.ThreadingHTTPServer(("0.0.0.0", _runtime.PORT), Handler).serve_forever()
