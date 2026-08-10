"""HA Doctor 0.10 Engine Candidate runtime."""

import json
import os
import threading
from urllib.parse import urlparse

import app_v090 as previous
from contracts_v100 import VERSION, REPORT_SCHEMA, SHARE_SCHEMA
from scanner_v100 import scan as scan_v100
from sharing_v100 import MODEL as SHARE_MODEL, build_markdown_summary, build_share_report

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v100

_original_enhance = previous.enhance_ui_v090

UI_PATCH_V100 = r"""
(function(){
  const renderOverviewLegacy100=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy100(r);
    const d=r.doctor_view||{},p=r.product_intelligence||{},proj=p.score_projection||{},ev=p.evidence_summary||{},noise=p.entity_noise||{},cov=p.diagnostic_coverage||{};
    const target=$('#view-overview');
    if(!target) return;
    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>HA Doctor 0.10 · Engine Candidate</h2><p>Priorisation explicable, preuve par diagnostic, projections multi-corrections et compression du bruit.</p></div>${badge((d.verdict||{}).label||'Diagnostic',(d.verdict||{}).code==='critical'?'fail':(d.verdict||{}).code==='healthy'?'pass':'warn')}</div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="card"><div class="muted">Projection 1 / 3 / 5</div><div class="miniBig">${proj?.after_top_1?.score??'—'} · ${proj?.after_top_3?.score??'—'} · ${proj?.after_top_5?.score??'—'}</div><div class="rootText">Score estimé après les corrections les plus rentables.</div></div>
        <div class="card"><div class="muted">Niveau de preuve</div><div class="miniBig">${ev.confirmed||0} / ${ev.probable||0} / ${ev.hypothesis||0}</div><div class="rootText">confirmé · probable · hypothèse</div></div>
        <div class="card"><div class="muted">Couverture diagnostic</div><div class="miniBig">${cov.score??'—'}/100</div><div class="rootText">Flux, automatisations, registres et quality gates combinés.</div></div>
      </div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${noise.raw_unavailable??0}</div><div class="muted">unavailable bruts · ${noise.registry_actionable_root_causes??0} causes registry actionnables</div></div>
        <div class="miniCard"><div class="miniBig">${noise.raw_unknown??0}</div><div class="muted">unknown bruts · ${noise.unknown_stateless_ignored??0} stateless ignorés</div></div>
        <div class="miniCard"><div class="miniBig">${r?.scan_performance?.total_seconds??r.scan_duration_seconds??'—'}s</div><div class="muted">scan · phase lente ${esc(r?.scan_performance?.slowest_phase||'—')}</div></div>
      </div>`);
  };

  const renderActionsLegacy100=renderActions;
  renderActions=function(r){
    renderActionsLegacy100(r);
    const items=(r?.doctor_view?.next_best_actions||[]).slice(0,10);
    const target=$('#view-actions');
    if(!target) return;
    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>Actions expliquées 0.10</h2><p>Chaque action expose le niveau de preuve, le risque calculé, la sécurité de réparation et le gain estimé.</p></div></div>
      <div class="grid" style="margin-bottom:18px">${items.map((x,i)=>`
        <div class="miniCard"><div class="rootHead"><strong>${i+1}. ${esc(x.title||x.id)}</strong>${badge(x.evidence_level||'hypothèse',x.evidence_level==='confirmed'?'pass':x.evidence_level==='probable'?'warn':'info')}</div>
        <div class="rootText">Risque ${esc(x.risk_score)}/100 · preuve ${esc(x.evidence_level||'—')} · ${esc(x.repair_safety||'manual')} · gain +${esc(x.estimated_score_gain||0)}</div></div>`).join('')||'<div class="muted">Aucune action.</div>'}</div>`);
  };

  const renderQualityLegacy100=renderQuality;
  renderQuality=function(r){
    renderQualityLegacy100(r);
    const p=r.product_intelligence||{},rel=p.automation_reliability||{},sec=p.security||{},maint=p.maintenance||{},self=r.self_check||{};
    const target=$('#view-quality');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Engine Candidate 0.10</h2><p>Le moteur vérifie aussi ses contrats de partage, ses projections et ses priorités de résilience.</p></div>${badge(self.status||'—',self.status==='pass'?'pass':self.status==='fail'?'fail':'warn')}</div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${rel.physical_controller_pairs_to_review??0}</div><div class="muted">conflit(s) physique(s) restant(s) · ${rel.numeric_overlap_candidate_pairs??0} overlap(s) numérique(s)</div></div>
        <div class="miniCard"><div class="miniBig">${sec.active_secret_hint_count??0}</div><div class="muted">secret(s) actif(s) potentiel(s) · posture ${esc(sec.posture||'—')}</div></div>
        <div class="miniCard"><div class="miniBig">${maint.probable_orphans??0}</div><div class="muted">orphelin(s) probable(s) · ${maint.missing_reference_count??0} référence(s) absente(s)</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v100(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str):
        return enhanced
    enhanced = enhanced.replace("Le contrôle technique de votre Home Assistant · Milestone", "Le contrôle technique de votre Home Assistant · Engine Candidate")
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "HA Doctor 0.10 · Engine Candidate" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V100 + "\n" + marker, 1)
    return enhanced


_runtime.enhance_ui_v080 = enhance_ui_v100


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path

        if path.endswith("/api/version") or path == "/api/version":
            return self._json({
                "product": "HA Doctor",
                "version": VERSION,
                "report_schema": REPORT_SCHEMA,
                "share_schema": SHARE_SCHEMA,
                "read_only": True,
                "automatic_fix": False,
                "engine_candidate": True,
            })

        if path.endswith("/api/intelligence") or path == "/api/intelligence":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "version": VERSION,
                "doctor_view": report.get("doctor_view") or {},
                "product_intelligence": report.get("product_intelligence") or {},
                "condition_semantics": report.get("condition_semantics") or {},
                "resilience_recommendations": report.get("resilience_recommendations") or {},
            })

        if path.endswith("/api/scan-performance") or path == "/api/scan-performance":
            report = self._report_or_404()
            if report is None:
                return
            return self._json(report.get("scan_performance") or {})

        if path.endswith("/api/self-check") or path == "/api/self-check":
            report = self._report_or_404()
            if report is None:
                return
            return self._json(report.get("self_check") or {})

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
                "Content-Disposition": 'attachment; filename="ha-doctor-support.json"',
                "X-HA-Doctor-Share-Bytes": str(len(data)),
                "X-HA-Doctor-Full-Bytes": str(int(meta.get("full_report_bytes_estimate", 0) or 0)),
                "X-HA-Doctor-Share-Model": SHARE_MODEL,
            }
            return self._bytes(data, "application/json; charset=utf-8", headers=headers)

        if path.endswith("/api/download-support-summary") or path == "/api/download-support-summary":
            report = self._report_or_404()
            if report is None:
                return
            data = build_markdown_summary(report).encode("utf-8")
            return self._bytes(data, "text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ha-doctor-summary.md"'})

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
