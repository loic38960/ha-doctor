"""HA Doctor 0.12 Temporal Truth Engine runtime."""

import json
import os
import threading
from urllib.parse import urlparse

import app_v110 as previous
from contracts_v120 import VERSION, REPORT_SCHEMA, SHARE_SCHEMA, HISTORY_CONTRACT
from scanner_v120 import scan as scan_v120
from sharing_v120 import MODEL as SHARE_MODEL, build_markdown_summary, build_share_report

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v120
_original_enhance = previous.enhance_ui_v110

UI_PATCH_V120 = r"""
(function(){
  const renderOverviewLegacy120=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy120(r);
    const p=r.product_intelligence||{},t=r.temporal_analysis||{},trace=p.score_change_trace||{},pub=p.public_contract_truth||{},hist=r.score_history_integrity||{};
    const target=$('#view-overview'); if(!target) return;
    const comparison=trace.comparison_status==='canonical'
      ? `${trace.previous_score??'—'} → ${trace.primary_score??'—'} (${(trace.score_delta??0)>=0?'+':''}${trace.score_delta??0})`
      : (trace.comparison_status==='legacy_untrusted'?'ancien historique non fiable':'premier snapshot canonique');
    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>HA Doctor 0.12 · Temporal Truth Engine</h2><p>Le score historique utilise désormais le score final publié, jamais une valeur intermédiaire devinée.</p></div>${badge((r.self_check||{}).status||'—',(r.self_check||{}).status==='pass'?'pass':'warn')}</div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="card"><div class="muted">Comparaison score</div><div class="miniBig">${esc(comparison)}</div><div class="rootText">${trace.previous_score_trusted?'snapshot canonique':'aucun faux delta produit'}</div></div>
        <div class="card"><div class="muted">Contrat historique</div><div class="miniBig">${hist.canonical_snapshots_last_10??0}</div><div class="rootText">snapshot(s) canonique(s) sur les 10 derniers · ${hist.legacy_untrusted_snapshots_last_10??0} legacy.</div></div>
        <div class="card"><div class="muted">Contrats publics</div><div class="miniBig">${pub.diagnostic_source_fresh&&pub.action_plan_model_fresh&&pub.controller_review_model_fresh&&pub.temporal_model_fresh?'OK':'À revoir'}</div><div class="rootText">plan, résumé contrôleurs, temporal et source diagnostique synchronisés.</div></div>
      </div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${t.false_stability_prevented?'1':'0'}</div><div class="muted">faux score stable empêché</div></div>
        <div class="miniCard"><div class="miniBig">${t.current_snapshot_canonicalized?'1':'0'}</div><div class="muted">snapshot courant canonisé</div></div>
        <div class="miniCard"><div class="miniBig">${t.current_snapshot_publication_complete?'1':'0'}</div><div class="muted">snapshot publié validé</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v120(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str):
        return enhanced
    enhanced = enhanced.replace("Le contrôle technique de votre Home Assistant · Cross-Validated Engine", "Le contrôle technique de votre Home Assistant · Temporal Truth Engine")
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "HA Doctor 0.12 · Temporal Truth Engine" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V120 + "\n" + marker, 1)
    return enhanced

_runtime.enhance_ui_v080 = enhance_ui_v120


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/version") or path == "/api/version":
            return self._json({"product": "HA Doctor", "version": VERSION, "report_schema": REPORT_SCHEMA, "share_schema": SHARE_SCHEMA, "history_contract": HISTORY_CONTRACT, "read_only": True, "automatic_fix": False, "temporal_truth_engine": True})
        if path.endswith("/api/temporal-truth") or path == "/api/temporal-truth":
            report = self._report_or_404()
            if report is None: return
            p = report.get("product_intelligence") or {}
            return self._json({"version": VERSION, "temporal_analysis": report.get("temporal_analysis") or {}, "score_history_integrity": report.get("score_history_integrity") or {}, "score_change_trace": p.get("score_change_trace") or {}, "public_contract_truth": p.get("public_contract_truth") or {}})
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
            return self._bytes(data, "application/json; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ha-doctor-support.json"', "X-HA-Doctor-Share-Bytes": str(len(data)), "X-HA-Doctor-Share-Model": SHARE_MODEL, "X-HA-Doctor-Temporal-Contract": HISTORY_CONTRACT, "X-HA-Doctor-Export-Validated": "true" if meta.get("within_hard_bytes") else "false"})
        if path.endswith("/api/download-support-summary") or path == "/api/download-support-summary":
            report = self._report_or_404()
            if report is None: return
            return self._bytes(build_markdown_summary(report).encode("utf-8"), "text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ha-doctor-summary.md"'})
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
