"""HA Doctor 0.9 product runtime.

The HTTP surface remains read-only. 0.9 adds a customer-oriented doctor view,
self-check endpoint and smaller support exports on top of the 0.8.8 runtime.
"""
import json
import os
import threading
from urllib.parse import urlparse

import app_v088 as previous
from scanner_v090 import scan as scan_v090
from sharing_v090 import MODEL as SHARE_MODEL, build_markdown_summary, build_share_report

VERSION = "0.9.0"
REPORT_SCHEMA = "ha-doctor-report/0.9"

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v090

_original_enhance = previous.enhance_ui_v088

UI_PATCH_V090 = r"""
(function(){
  const actions=document.querySelector('.actions');
  const share=document.getElementById('shareBtn');
  if(actions && !document.getElementById('supportSummaryBtn')){
    const summary=document.createElement('a');
    summary.id='supportSummaryBtn';
    summary.className='btn ghost';
    summary.href=api('download-support-summary');
    summary.textContent='Résumé lisible';
    summary.title='Rapport Markdown court avec verdict et prochaines actions';
    if(share && share.nextSibling) actions.insertBefore(summary,share.nextSibling);
    else actions.appendChild(summary);
  }
  if(share){
    share.textContent='Rapport support · compact';
    share.href=api('download-share');
    share.title='Export support V3 borné, centré sur les actions et la confiance du diagnostic';
  }

  const renderOverviewLegacy090=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy090(r);
    const d=r.doctor_view||{},v=d.verdict||{},t=d.triage_counts||{},trust=d.trust||{},noise=d.noise_reduction||{},self=r.self_check||{};
    const next=d.next_action||{};
    const target=$('#view-overview');
    if(!target) return;
    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>HA Doctor 0.9 · Triage produit</h2><p>Une réponse courte avant les détails techniques : état, prochaine action, confiance et impact.</p></div>${badge(v.label||'Diagnostic',v.code==='healthy'?'pass':v.code==='critical'?'fail':'warn')}</div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="card"><div class="muted">Verdict</div><div class="miniBig">${esc(v.label||'—')}</div><div class="rootText">Score technique ${d.technical_health_score??r?.scores?.global??'—'}/100 · preview ${d.score_v5_preview??'—'}/100.</div></div>
        <div class="card"><div class="muted">Prochaine action</div><div class="rootTitle">${esc(next.title||'Aucune action prioritaire')}</div><div class="rootText">${next.id?`Risque ${esc(next.risk_score)}/100 · confiance ${esc(next.confidence_tier)} · ${esc(next.effort)}`:'Le plan ne contient rien de prioritaire.'}</div></div>
        <div class="card"><div class="muted">Confiance HA Doctor</div><div class="miniBig">${esc(trust.score??'—')}/100</div><div class="rootText">${esc(trust.level||'—')} · auto-contrôle ${esc(self.status||'—')}.</div></div>
      </div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${t.fix_now||0}</div><div class="muted">à corriger maintenant</div></div>
        <div class="miniCard"><div class="miniBig">${t.investigate||0}</div><div class="muted">à investiguer</div></div>
        <div class="miniCard"><div class="miniBig">${Math.round(Number(noise.noise_or_observation_compression_ratio||0)*100)}%</div><div class="muted">diagnostics gardés hors plan / bruit comprimé</div></div>
      </div>`);
  };

  const renderActionsLegacy090=renderActions;
  renderActions=function(r){
    renderActionsLegacy090(r);
    const d=r.doctor_view||{};
    const target=$('#view-actions');
    if(!target) return;
    const items=(d.next_best_actions||[]).slice(0,7);
    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>Ordre recommandé 0.9</h2><p>Risque, confiance, blast radius et gain potentiel sont réunis dans un ordre client unique.</p></div></div>
      <div class="grid" style="margin-bottom:18px">${items.map((x,i)=>`
        <div class="miniCard"><div class="rootHead"><strong>${i+1}. ${esc(x.title||x.id)}</strong>${badge(x.lane||'review',x.lane==='fix_now'?'action_now':x.lane==='optimize'?'optimize':'verify')}</div>
        <div class="rootText">Risque ${esc(x.risk_score)}/100 · confiance ${esc(x.confidence_tier)} · effort ${esc(x.effort)}${Number(x.estimated_score_gain||0)>0?` · gain estimé +${esc(x.estimated_score_gain)}`:''}</div></div>`).join('')||'<div class="muted">Aucune action prioritaire.</div>'}</div>`);
  };

  const renderQualityLegacy090=renderQuality;
  renderQuality=function(r){
    renderQualityLegacy090(r);
    const self=r.self_check||{},trust=r.diagnostic_trust||r?.doctor_view?.trust||{};
    const target=$('#view-quality');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Auto-contrôle 0.9</h2><p>HA Doctor vérifie son propre contrat de rapport avant de te présenter ses conclusions.</p></div>${badge(self.status||'—',self.status==='pass'?'pass':self.status==='fail'?'fail':'warn')}</div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${self.pass_count||0}/${self.check_count||0}</div><div class="muted">contrôles internes réussis</div></div>
        <div class="miniCard"><div class="miniBig">${self.warning_count||0}</div><div class="muted">avertissement(s) d'auto-contrôle</div></div>
        <div class="miniCard"><div class="miniBig">${trust.score??'—'}</div><div class="muted">indice de confiance du diagnostic</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v090(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str):
        return enhanced
    enhanced = enhanced.replace("Le contrôle technique de votre Home Assistant · Alpha", "Le contrôle technique de votre Home Assistant · Milestone")
    enhanced = enhanced.replace("HA Doctor 0.8 corrèle", "HA Doctor 0.9 priorise et corrèle")
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "HA Doctor 0.9 · Triage produit" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V090 + "\n" + marker, 1)
    return enhanced


_runtime.enhance_ui_v080 = enhance_ui_v090


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path

        if path.endswith("/api/version") or path == "/api/version":
            return self._json({
                "product": "HA Doctor",
                "version": VERSION,
                "report_schema": REPORT_SCHEMA,
                "share_schema": "ha-doctor-share/3",
                "read_only": True,
                "automatic_fix": False,
                "milestone_release": True,
            })

        if path.endswith("/api/doctor-view") or path == "/api/doctor-view":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "version": VERSION,
                "doctor_view": report.get("doctor_view") or {},
                "triage_board": report.get("triage_board") or {},
                "change_digest": report.get("change_digest") or {},
            })

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
            return self._bytes(
                data,
                "text/markdown; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="ha-doctor-summary.md"'},
            )

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
