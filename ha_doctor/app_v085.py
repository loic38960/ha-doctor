"""HA Doctor 0.8.5 runtime wrapper."""
import os
import threading
from urllib.parse import urlparse

import app_v084 as previous
from scanner_v085 import scan as scan_v085

VERSION = "0.8.5"
REPORT_SCHEMA = "ha-doctor-report/0.8.5"

# Propagate the final runtime version through the layered wrappers. 0.8.5 only
# replaces the scanner entrypoint; all earlier API/UI compatibility stays live.
previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.VERSION = VERSION
previous.previous.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.calibrated.VERSION = VERSION
previous.previous.calibrated.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.calibrated.hardened.VERSION = VERSION
previous.previous.calibrated.hardened.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.calibrated.hardened.runtime.VERSION = VERSION
previous.previous.calibrated.hardened.runtime.REPORT_SCHEMA = REPORT_SCHEMA
previous.previous.calibrated.hardened.runtime.legacy.VERSION = VERSION
previous.previous.calibrated.hardened.runtime.legacy.scan = scan_v085

_runtime = previous.previous.calibrated.hardened.runtime.legacy
_original_compact = _runtime.compact_report
_original_insights = _runtime.insights_report
_original_enhance = previous.enhance_ui_v084

UI_PATCH_V085 = r"""
(function(){
  const renderOverviewLegacy085=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy085(r);
    const s=r.condition_semantics||{},v5=r.score_v5_preview||{},c=r.consistency_analysis||{};
    const target=$('#view-overview');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Branch Intelligence 0.8.5</h2><p>HA Doctor suit les chemins d'action avant de conclure à un conflit entre contrôleurs.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${s.branch_protocol_resolved_pair_count||0}</div><div class="muted">paire(s) expliquée(s) par analyse de branche</div></div>
        <div class="miniCard"><div class="miniBig">${s.physical_unproven_pair_count||0}</div><div class="muted">paire(s) physique(s) restant à vérifier</div></div>
        <div class="miniCard"><div class="miniBig">${v5.v5_preview_score ?? r?.scores?.global ?? '—'}</div><div class="muted">Preview Score V5 · usage-aware · non appliqué</div></div>
      </div>
      <div class="miniCard"><strong>Cohérence croisée</strong><div class="rootText">${c.failure_count||0} échec(s) · snapshot, architecture, résumé, contrôleurs et projection V5 vérifiés ensemble.</div></div>`);
  };

  const renderQualityLegacy085=renderQuality;
  renderQuality=function(r){
    renderQualityLegacy085(r);
    const s=r.condition_semantics||{},c=r.consistency_analysis||{},v5=r.score_v5_preview||{};
    const target=$('#view-quality');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Validation 0.8.5</h2><p>Les conflits sont évalués au niveau des branches, et les compteurs du rapport sont recroisés avant publication.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${s.protocol_coordinated_pair_count||0}</div><div class="muted">handoff(s) explicables au total</div></div>
        <div class="miniCard"><div class="miniBig">${s.branch_protocol_resolved_pair_count||0}</div><div class="muted">preuve(s) branch-aware</div></div>
        <div class="miniCard"><div class="miniBig">${c.failure_count||0}</div><div class="muted">incohérence(s) croisée(s) · modèle ${v5.model||'—'}</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v085(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str):
        return enhanced
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "Branch Intelligence 0.8.5" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V085 + "\n" + marker, 1)
    return enhanced


previous.previous.calibrated.hardened.runtime.enhance_ui_v080 = enhance_ui_v085


def compact_report_v085(report):
    payload = _original_compact(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "entity_lineage", "flow_confidence", "condition_semantics",
        "resilience_analysis", "resilience_recommendations", "root_cause_summary",
        "temporal_analysis", "consistency_analysis", "quality_gates", "score_v5_preview",
    ):
        payload[key] = report.get(key) or {}
    return payload


def insights_report_v085(report):
    payload = _original_insights(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "entity_lineage", "flow_confidence", "condition_semantics",
        "resilience_analysis", "resilience_recommendations", "root_cause_summary",
        "temporal_analysis", "consistency_analysis", "quality_gates", "score_v5_preview",
    ):
        payload[key] = report.get(key) or {}
    return payload


_runtime.compact_report = compact_report_v085
_runtime.insights_report = insights_report_v085


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/branch-semantics") or path == "/api/branch-semantics":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "version": VERSION,
                "condition_semantics": report.get("condition_semantics") or {},
                "score_v5_preview": report.get("score_v5_preview") or {},
                "consistency_analysis": report.get("consistency_analysis") or {},
                "quality_gates": report.get("quality_gates") or {},
            })
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
