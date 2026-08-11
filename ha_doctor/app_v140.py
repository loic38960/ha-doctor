"""HA Doctor 0.14 Consolidated Decision Engine runtime."""

import json
import os
import threading
from urllib.parse import urlparse

import app_v130 as previous
from contracts_v140 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, HISTORY_CONTRACT, HISTORY_POLICY,
    DECISION_MODEL, CONDITION_MODEL,
)
from scanner_v140 import scan as scan_v140
from sharing_v140 import MODEL as SHARE_MODEL, build_markdown_summary, build_share_report

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v140
_original_enhance = previous.enhance_ui_v130

UI_PATCH_V140 = r"""
(function(){
  const renderOverviewLegacy140=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy140(r);
    const d=r.decision_engine||{}, lanes=d.lane_counts||{}, sem=r.condition_semantics||{}, t=r.temporal_analysis||{}, sc=r.self_check||{};
    const target=$('#view-overview'); if(!target) return;
    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>HA Doctor 0.14 · Consolidated Decision Engine</h2><p>Un pipeline unique : acquisition, preuves, décisions, auto-contrôle natif, publication et historique.</p></div>${badge(sc.status||'—',sc.status==='pass'?'pass':(sc.status==='warning'?'warn':'fail'))}</div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="card"><div class="muted">À corriger</div><div class="miniBig">${lanes.fix_now??0}</div><div class="rootText">actions à preuve forte et playbook manuel.</div></div>
        <div class="card"><div class="muted">Revue logique</div><div class="miniBig">${lanes.logic_review??0}</div><div class="rootText">arbitrages et dépendances qui nécessitent de comprendre l'intention.</div></div>
        <div class="card"><div class="muted">Surveillance externe</div><div class="miniBig">${lanes.watch??0}</div><div class="rootText">incidents sans blast radius automation actuel.</div></div>
      </div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="miniCard"><div class="miniBig">${sem.policy_overlap_pair_count??0}</div><div class="muted">overlap(s) de politique</div></div>
        <div class="miniCard"><div class="miniBig">${sem.branch_numeric_resolved_pair_count??0}</div><div class="muted">exclusion(s) numérique(s) prouvée(s)</div></div>
        <div class="miniCard"><div class="miniBig">${sc.check_count??0}</div><div class="muted">contrôles natifs, sans réécriture legacy</div></div>
      </div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${t.previous_score_trusted?'oui':'non'}</div><div class="muted">score précédent publié fiable</div></div>
        <div class="miniCard"><div class="miniBig">${t.blocked_unpublished_snapshots_last_10??0}</div><div class="muted">scan(s) bloqué(s) exclus de l'historique score</div></div>
        <div class="miniCard"><div class="miniBig">0</div><div class="muted">lecture HA supplémentaire</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v140(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str): return enhanced
    enhanced = enhanced.replace("Le contrôle technique de votre Home Assistant · Decision Engine", "Le contrôle technique de votre Home Assistant · Consolidated Decision Engine")
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "HA Doctor 0.14 · Consolidated Decision Engine" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V140 + "\n" + marker, 1)
    return enhanced

_runtime.enhance_ui_v080 = enhance_ui_v140


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/version") or path == "/api/version":
            return self._json({
                "product": "HA Doctor", "version": VERSION, "report_schema": REPORT_SCHEMA,
                "share_schema": SHARE_SCHEMA, "history_contract": HISTORY_CONTRACT, "history_policy": HISTORY_POLICY,
                "decision_model": DECISION_MODEL, "condition_model": CONDITION_MODEL,
                "consolidated_pipeline": True, "native_self_check": True,
                "read_only": True, "automatic_fix": False,
            })
        if path.endswith("/api/operational-decisions") or path == "/api/operational-decisions":
            report = self._report_or_404()
            if report is None: return
            return self._json({
                "version": VERSION, "decision_engine": report.get("decision_engine") or {},
                "controller_review_summary": report.get("controller_review_summary") or {},
                "release_readiness": report.get("release_readiness") or {},
            })
        if path.endswith("/api/publication-truth") or path == "/api/publication-truth":
            report = self._report_or_404()
            if report is None: return
            return self._json({
                "version": VERSION, "temporal_analysis": report.get("temporal_analysis") or {},
                "score_history_integrity": report.get("score_history_integrity") or {},
                "self_check": report.get("self_check") or {}, "release_readiness": report.get("release_readiness") or {},
            })
        if path.endswith("/api/share-report") or path == "/api/share-report":
            report = self._report_or_404()
            if report is None: return
            return self._json(build_share_report(report))
        if path.endswith("/api/download-share") or path == "/api/download-share":
            report = self._report_or_404()
            if report is None: return
            payload = build_share_report(report); data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            meta = payload.get("export_meta") or {}
            return self._bytes(data, "application/json; charset=utf-8", headers={
                "Content-Disposition": 'attachment; filename="ha-doctor-support.json"',
                "X-HA-Doctor-Share-Bytes": str(len(data)), "X-HA-Doctor-Share-Model": SHARE_MODEL,
                "X-HA-Doctor-History-Policy": HISTORY_POLICY,
                "X-HA-Doctor-Export-Validated": "true" if meta.get("within_hard_bytes") else "false",
            })
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
