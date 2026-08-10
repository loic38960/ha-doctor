"""HA Doctor 0.8.2 runtime wrapper.

Reuses the stable 0.8.1 HTTP/UI wrapper and swaps in the calibrated 0.8.2
scanner. The primary Score V4 remains unchanged; contextual scoring is exposed
as a preview only.
"""

import os
import threading
from urllib.parse import urlparse

import app_v081 as hardened
from scanner_v082 import scan as scan_v082

VERSION = "0.8.2"
REPORT_SCHEMA = "ha-doctor-report/0.8.2"

hardened.VERSION = VERSION
hardened.REPORT_SCHEMA = REPORT_SCHEMA
hardened.runtime.VERSION = VERSION
hardened.runtime.REPORT_SCHEMA = REPORT_SCHEMA
hardened.runtime.legacy.VERSION = VERSION
hardened.runtime.legacy.scan = scan_v082

_original_compact = hardened.runtime.legacy.compact_report
_original_insights = hardened.runtime.legacy.insights_report
_original_enhance_ui = hardened.runtime.enhance_ui_v080


UI_PATCH_V082 = r"""
(function(){
  const pct082=value=>value==null?'—':`${Math.round(Number(value)*100)}%`;
  const qstatus082=value=>value==='pass'?'pass':'warn';

  const renderOverviewLegacy082=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy082(r);
    const p=r.contextual_score_preview||{},q=r.quality_gates||{},root=r.root_cause_summary||{};
    const target=$('#view-overview');
    if(!target) return;
    const tech=p.technical_score ?? r?.scores?.global ?? '—';
    const contextual=p.contextual_score ?? tech;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Calibration 0.8.2</h2><p>Le score technique reste comparable à l’historique ; le contexte et la confiance sont affichés séparément.</p></div>${badge(q.overall||'n/a',qstatus082(q.overall))}</div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${tech}</div><div class="muted">Score V4 technique</div></div>
        <div class="miniCard"><div class="miniBig">${contextual}</div><div class="muted">preview contextualisé${Number(p.delta||0)!==0?` · ${Number(p.delta)>0?'+':''}${p.delta}`:''}</div></div>
        <div class="miniCard"><div class="miniBig">${root.actionable_registry_incidents||0}/${root.detected_registry_incidents||0}</div><div class="muted">causes registry actionnables / détectées</div></div>
      </div>`);
  };

  const renderQualityLegacy082=renderQuality;
  renderQuality=function(r){
    renderQualityLegacy082(r);
    const f=r.flow_confidence||{},s=r.condition_semantics||{},res=r.resilience_analysis||{};
    const target=$('#view-quality');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Fiabilité du diagnostic 0.8.2</h2><p>HA Doctor distingue désormais « compris » de « prouvé » et un vrai fallback d’une simple valeur par défaut.</p></div></div>
      <div class="grid grid3">
        <div class="card"><div class="rootHead"><strong>Confiance des flux</strong>${badge(f.quality_status||'n/a',qstatus082(f.quality_status))}</div><div class="miniBig">${pct082(f.low_confidence_ratio||0)}</div><div class="rootText">cibles dynamiques à confiance réduite · ${f.unresolved_dynamic_targets||0} non résolue(s).</div></div>
        <div class="card"><div class="rootHead"><strong>Contrôleurs</strong>${badge(String(s.unproven_pair_count||0),(s.unproven_pair_count||0)?'warn':'pass')}</div><div class="miniBig">${s.resolved_pair_count||0}</div><div class="rootText">paire(s) résolue(s) · ${s.coordinated_pair_count||0} coordination(s) · ${s.unproven_pair_count||0} à vérifier.</div></div>
        <div class="card"><div class="rootHead"><strong>Résilience</strong>${badge((res.review_count||res.partial_count)?'À vérifier':'Protégée',(res.review_count||res.partial_count)?'warn':'pass')}</div><div class="miniBig">${res.protected_count||0}</div><div class="rootText">protégée(s) · ${res.partial_count||0} partielle(s) · ${res.review_count||0} à revoir · ${res.numeric_default_only_count||0} défaut(s) numérique(s) faibles.</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v082(html):
    enhanced = _original_enhance_ui(html)
    if not isinstance(enhanced, str):
        return enhanced
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "Calibration 0.8.2" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V082 + "\n" + marker, 1)
    return enhanced


hardened.runtime.enhance_ui_v080 = enhance_ui_v082


def compact_report_v082(report):
    payload = _original_compact(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "contextual_score_preview",
        "flow_confidence",
        "condition_semantics",
        "resilience_analysis",
        "root_cause_summary",
    ):
        payload[key] = report.get(key) or {}
    return payload


def insights_report_v082(report):
    payload = _original_insights(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "contextual_score_preview",
        "flow_confidence",
        "condition_semantics",
        "resilience_analysis",
        "root_cause_summary",
        "quality_gates",
    ):
        payload[key] = report.get(key) or {}
    return payload


hardened.runtime.legacy.compact_report = compact_report_v082
hardened.runtime.legacy.insights_report = insights_report_v082


class Handler(hardened.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/calibration") or path == "/api/calibration":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "version": VERSION,
                "contextual_score_preview": report.get("contextual_score_preview") or {},
                "flow_confidence": report.get("flow_confidence") or {},
                "condition_semantics": report.get("condition_semantics") or {},
                "resilience_analysis": report.get("resilience_analysis") or {},
                "root_cause_summary": report.get("root_cause_summary") or {},
                "quality_gates": report.get("quality_gates") or {},
            })
        return super().do_GET()


if __name__ == "__main__":
    print(f"[HA Doctor] process started ({VERSION})", flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START", "true").lower() in {"1", "true", "yes", "on"}:
        def initial_scan():
            try:
                hardened.runtime.legacy.run_scan()
                print("[HA Doctor] initial scan complete", flush=True)
            except Exception as exc:
                print(
                    f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )

        threading.Thread(target=initial_scan, daemon=True).start()

    print(f"[HA Doctor] web server listening on {hardened.runtime.legacy.PORT}", flush=True)
    hardened.runtime.legacy.ThreadingHTTPServer(
        ("0.0.0.0", hardened.runtime.legacy.PORT), Handler
    ).serve_forever()
