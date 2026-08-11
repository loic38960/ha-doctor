"""HA Doctor 0.17 Resolution & Attribution runtime."""

import json
import os
import threading
from urllib.parse import urlparse

import app_v160 as previous
from contracts_v170 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, HISTORY_CONTRACT, HISTORY_POLICY, PUBLICATION_MODEL,
    DECISION_MODEL, CONDITION_MODEL, FEEDBACK_MODEL, DUPLICATE_MODEL, REFERENCE_MODEL,
    SCORE_ATTRIBUTION_MODEL,
)
from scanner_v170 import scan as scan_v170
from sharing_v170 import MODEL as SHARE_MODEL, build_markdown_summary, build_share_report

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v170
_original_enhance = previous.enhance_ui_v160

UI_PATCH_V170 = r"""
(function(){
  const renderOverviewLegacy170=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy170(r);
    const d=r.decision_engine||{}, lanes=d.lane_counts||{}, res=d.resolution_counts||{}, a=r.score_attribution||{}, fb=r.automation_feedback_semantics||{}, dup=r.duplicate_action_semantics||{}, refs=r.missing_reference_intelligence||{}, sc=r.self_check||{};
    const target=$('#view-overview'); if(!target) return;
    const attr=a.status==='attributed' ? `${a.primary_delta>0?'+':''}${a.primary_delta??0}` : (a.status==='baseline_domain_detail_unavailable'?'baseline sans détail':'—');
    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>HA Doctor 0.17 · Resolution & Attribution Engine</h2><p>Résout statiquement ce qui peut l'être avant de demander une revue manuelle, puis explique les futurs mouvements de score par domaine.</p></div>${badge(sc.status||'—',sc.status==='pass'?'pass':(sc.status==='warning'?'warn':'fail'))}</div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="card"><div class="muted">Corrections prêtes</div><div class="miniBig">${res.manual_fix_ready??0}</div><div class="rootText">modifications manuelles avec preuve suffisante.</div></div>
        <div class="card"><div class="muted">Revue logique</div><div class="miniBig">${res.logic_review_required??0}</div><div class="rootText">points qui nécessitent encore l'intention humaine.</div></div>
        <div class="card"><div class="muted">Résolues statiquement</div><div class="miniBig">${res.statically_resolved??0}</div><div class="rootText">relations déclassées sans masquer le diagnostic source.</div></div>
      </div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="miniCard"><div class="miniBig">${dup.manual_fix_ready_count??0}</div><div class="muted">doublon(s) exact(s) prêt(s) à corriger</div></div>
        <div class="miniCard"><div class="miniBig">${fb.statically_resolved_count??0}</div><div class="muted">feedback(s) résolu(s) statiquement</div></div>
        <div class="miniCard"><div class="miniBig">${refs.runtime_relevant_count??0}</div><div class="muted">référence(s) absente(s) à impact runtime</div></div>
      </div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${lanes.fix_now??0}</div><div class="muted">fix-now dans l'ordre canonique</div></div>
        <div class="miniCard"><div class="miniBig">${lanes.watch??0}</div><div class="muted">surveillance sans impact prioritaire</div></div>
        <div class="miniCard"><div class="miniBig">${attr}</div><div class="muted">attribution du delta de score</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v170(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str): return enhanced
    enhanced = enhanced.replace("Le contrôle technique de votre Home Assistant · Evidence Precision Engine", "Le contrôle technique de votre Home Assistant · Resolution & Attribution Engine")
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "HA Doctor 0.17 · Resolution & Attribution Engine" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V170 + "\n" + marker, 1)
    return enhanced

_runtime.enhance_ui_v080 = enhance_ui_v170


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path=urlparse(self.path).path
        if path.endswith("/api/version") or path=="/api/version":
            return self._json({
                "product":"HA Doctor","version":VERSION,"report_schema":REPORT_SCHEMA,"share_schema":SHARE_SCHEMA,
                "history_contract":HISTORY_CONTRACT,"history_policy":HISTORY_POLICY,"publication_model":PUBLICATION_MODEL,
                "decision_model":DECISION_MODEL,"condition_model":CONDITION_MODEL,"feedback_model":FEEDBACK_MODEL,
                "duplicate_model":DUPLICATE_MODEL,"reference_model":REFERENCE_MODEL,"score_attribution_model":SCORE_ATTRIBUTION_MODEL,
                "resolution_engine":True,"domain_score_history":True,"read_only":True,"automatic_fix":False,
            })
        if path.endswith("/api/resolution") or path=="/api/resolution":
            report=self._report_or_404()
            if report is None:return
            return self._json({
                "version":VERSION,"resolution_summary":report.get("resolution_summary") or {},
                "decision_engine":report.get("decision_engine") or {},
                "automation_resolution":report.get("automation_resolution") or {},
                "missing_reference_intelligence":report.get("missing_reference_intelligence") or {},
            })
        if path.endswith("/api/score-attribution") or path=="/api/score-attribution":
            report=self._report_or_404()
            if report is None:return
            return self._json({"version":VERSION,"score_attribution":report.get("score_attribution") or {},"temporal_analysis":report.get("temporal_analysis") or {}})
        if path.endswith("/api/resilience-guards") or path=="/api/resilience-guards":
            report=self._report_or_404()
            if report is None:return
            return self._json({"version":VERSION,"resilience_recommendations":report.get("resilience_recommendations") or {},"resilience_precision":report.get("resilience_precision") or {}})
        if path.endswith("/api/share-report") or path=="/api/share-report":
            report=self._report_or_404()
            if report is None:return
            return self._json(build_share_report(report))
        if path.endswith("/api/download-share") or path=="/api/download-share":
            report=self._report_or_404()
            if report is None:return
            payload=build_share_report(report); data=json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode("utf-8"); meta=payload.get("export_meta") or {}
            return self._bytes(data,"application/json; charset=utf-8",headers={
                "Content-Disposition":'attachment; filename="ha-doctor-support.json"',
                "X-HA-Doctor-Share-Bytes":str(len(data)),"X-HA-Doctor-Share-Model":SHARE_MODEL,
                "X-HA-Doctor-Resolution":"true","X-HA-Doctor-Attribution":str((payload.get("temporal_truth") or {}).get("score_attribution",{}).get("status") or "unknown"),
                "X-HA-Doctor-Export-Validated":"true" if meta.get("within_hard_bytes") else "false",
            })
        if path.endswith("/api/download-support-summary") or path=="/api/download-support-summary":
            report=self._report_or_404()
            if report is None:return
            return self._bytes(build_markdown_summary(report).encode("utf-8"),"text/markdown; charset=utf-8",headers={"Content-Disposition":'attachment; filename="ha-doctor-summary.md"'})
        return super().do_GET()


if __name__=="__main__":
    print(f"[HA Doctor] process started ({VERSION})",flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START","true").lower() in {"1","true","yes","on"}:
        def initial_scan():
            try:
                _runtime.run_scan(); print("[HA Doctor] initial scan complete",flush=True)
            except Exception as exc:
                print(f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}",flush=True)
        threading.Thread(target=initial_scan,daemon=True).start()
    print(f"[HA Doctor] web server listening on {_runtime.PORT}",flush=True)
    _runtime.ThreadingHTTPServer(("0.0.0.0",_runtime.PORT),Handler).serve_forever()
