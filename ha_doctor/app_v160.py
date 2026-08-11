"""HA Doctor 0.16 Evidence Precision Engine runtime."""

import json
import os
import threading
from urllib.parse import urlparse

import app_v150 as previous
from contracts_v160 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, HISTORY_CONTRACT, HISTORY_POLICY,
    PUBLICATION_MODEL, DECISION_MODEL, CONDITION_MODEL, CONTROLLER_IMPACT_MODEL,
)
from scanner_v160 import scan as scan_v160
from sharing_v160 import MODEL as SHARE_MODEL, build_markdown_summary, build_share_report

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v160
_original_enhance = previous.enhance_ui_v150

UI_PATCH_V160 = r"""
(function(){
  const renderOverviewLegacy160=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy160(r);
    const d=r.decision_engine||{}, lanes=d.lane_counts||{}, impact=r.controller_impact||{}, rec=(r.resilience_recommendations||{}), dup=r.duplicate_action_semantics||{}, fb=r.automation_feedback_semantics||{}, t=r.temporal_analysis||{}, sc=r.self_check||{};
    const target=$('#view-overview'); if(!target) return;
    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>HA Doctor 0.16 · Evidence Precision Engine</h2><p>Priorité au scope réellement non résolu : impact exact, phase de dépendance, feedback et ordre canonique.</p></div>${badge(sc.status||'—',sc.status==='pass'?'pass':(sc.status==='warning'?'warn':'fail'))}</div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="card"><div class="muted">À corriger</div><div class="miniBig">${lanes.fix_now??0}</div><div class="rootText">actions manuelles prioritaires.</div></div>
        <div class="card"><div class="muted">Revue logique</div><div class="miniBig">${lanes.logic_review??0}</div><div class="rootText">logique restante après réduction du bruit.</div></div>
        <div class="card"><div class="muted">Surveillance</div><div class="miniBig">${lanes.watch??0}</div><div class="rootText">incidents externes sans impact actuel.</div></div>
      </div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="miniCard"><div class="miniBig">${impact.physical_pair_count??0}</div><div class="muted">paire(s) physique(s) réellement ouverte(s)</div></div>
        <div class="miniCard"><div class="miniBig">${impact.impacted_automation_count??0}</div><div class="muted">automation(s) dans ce scope exact</div></div>
        <div class="miniCard"><div class="miniBig">${rec.must_fix_count??0}/${rec.hardening_count??0}</div><div class="muted">résilience must-fix / hardening</div></div>
      </div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${dup.count??0}</div><div class="muted">doublon(s) d'action exact(s) classifié(s)</div></div>
        <div class="miniCard"><div class="miniBig">${fb.count??0}</div><div class="muted">feedback(s) automation classifié(s)</div></div>
        <div class="miniCard"><div class="miniBig">${t.current_committed_baseline?'oui':'non'}</div><div class="muted">scan courant baseline canonique</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v160(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str): return enhanced
    enhanced = enhanced.replace("Le contrôle technique de votre Home Assistant · Trust & Publication Engine", "Le contrôle technique de votre Home Assistant · Evidence Precision Engine")
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "HA Doctor 0.16 · Evidence Precision Engine" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V160 + "\n" + marker, 1)
    return enhanced

_runtime.enhance_ui_v080 = enhance_ui_v160


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/version") or path == "/api/version":
            return self._json({
                "product": "HA Doctor", "version": VERSION, "report_schema": REPORT_SCHEMA,
                "share_schema": SHARE_SCHEMA, "history_contract": HISTORY_CONTRACT, "history_policy": HISTORY_POLICY,
                "publication_model": PUBLICATION_MODEL, "decision_model": DECISION_MODEL,
                "condition_model": CONDITION_MODEL, "controller_impact_model": CONTROLLER_IMPACT_MODEL,
                "evidence_precision": True, "canonical_decision_order": True,
                "read_only": True, "automatic_fix": False,
            })
        if path.endswith("/api/evidence-precision") or path == "/api/evidence-precision":
            report = self._report_or_404()
            if report is None: return
            return self._json({
                "version": VERSION, "controller_impact": report.get("controller_impact") or {},
                "resilience_precision": report.get("resilience_precision") or {},
                "resilience_recommendations": report.get("resilience_recommendations") or {},
                "duplicate_action_semantics": report.get("duplicate_action_semantics") or {},
                "automation_feedback_semantics": report.get("automation_feedback_semantics") or {},
            })
        if path.endswith("/api/decision-order") or path == "/api/decision-order":
            report = self._report_or_404()
            if report is None: return
            return self._json({
                "version": VERSION, "canonical_decision_order": report.get("canonical_decision_order") or {},
                "top_actions": (report.get("diagnostic_summary") or {}).get("top_actions") or [],
                "decision_summary": (report.get("doctor_view") or {}).get("decision_summary") or {},
            })
        if path.endswith("/api/published-baseline") or path == "/api/published-baseline":
            report = self._report_or_404()
            if report is None: return
            return self._json({
                "version": VERSION, "temporal_analysis": report.get("temporal_analysis") or {},
                "score_history_integrity": report.get("score_history_integrity") or {},
                "publication_transaction": report.get("publication_transaction") or {},
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
                "X-HA-Doctor-Precision-Scope": "unresolved-physical-only",
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
