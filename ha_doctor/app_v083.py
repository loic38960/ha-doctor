"""HA Doctor 0.8.3 runtime wrapper."""
import os
import threading
from urllib.parse import urlparse

import app_v082 as calibrated
from scanner_v083 import scan as scan_v083

VERSION = "0.8.3"
REPORT_SCHEMA = "ha-doctor-report/0.8.3"

# Propagate the runtime version through the layered wrappers and replace only
# the scanner entrypoint.
calibrated.VERSION = VERSION
calibrated.REPORT_SCHEMA = REPORT_SCHEMA
calibrated.hardened.VERSION = VERSION
calibrated.hardened.REPORT_SCHEMA = REPORT_SCHEMA
calibrated.hardened.runtime.VERSION = VERSION
calibrated.hardened.runtime.REPORT_SCHEMA = REPORT_SCHEMA
calibrated.hardened.runtime.legacy.VERSION = VERSION
calibrated.hardened.runtime.legacy.scan = scan_v083

_original_compact = calibrated.hardened.runtime.legacy.compact_report
_original_insights = calibrated.hardened.runtime.legacy.insights_report
_original_enhance_ui = calibrated.enhance_ui_v082


UI_PATCH_V083 = r"""
(function(){
  const pct083=value=>value==null?'—':`${Math.round(Number(value)*100)}%`;
  const renderOverviewLegacy083=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy083(r);
    const v5=r.score_v5_preview||{},t=r.temporal_analysis||{},root=r.root_cause_summary||{};
    const target=$('#view-overview');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Hardening 0.8.3</h2><p>Persistance qualifiée par le temps, blast radius registry et projection des corrections.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${v5.v5_preview_score ?? r?.scores?.global ?? '—'}</div><div class="muted">Preview Score V5 · non appliqué</div></div>
        <div class="miniCard"><div class="miniBig">${v5.projected_after_top_3_fixes ?? '—'}</div><div class="muted">projection après 3 corrections</div></div>
        <div class="miniCard"><div class="miniBig">${t.persistent_count||0}</div><div class="muted">persistant(s) · rescans rapides neutralisés</div></div>
      </div>
      <div class="miniCard"><strong>Blast radius registry</strong><div class="rootText">${root.registry_impacted_automation_count||0} automatisation(s) corrélée(s) · ${root.registry_high_or_critical_incident_count||0} cause(s) à fort impact.</div></div>`);
  };

  const renderQualityLegacy083=renderQuality;
  renderQuality=function(r){
    renderQualityLegacy083(r);
    const f=r.flow_confidence||{},s=r.condition_semantics||{},res=r.resilience_analysis||{},c=r.consistency_analysis||{};
    const target=$('#view-quality');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Validation 0.8.3</h2><p>Les avertissements ciblent maintenant les incertitudes qui demandent réellement une revue humaine.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${pct083(f.review_required_ratio||0)}</div><div class="muted">flux dynamiques réellement à revoir</div></div>
        <div class="miniCard"><div class="miniBig">${s.physical_unproven_pair_count||0}</div><div class="muted">paires physiques non prouvées · ${s.helper_unproven_pair_count||0} helper(s) séparé(s)</div></div>
        <div class="miniCard"><div class="miniBig">${c.failure_count||0}</div><div class="muted">incohérence(s) interne(s) · ${res.configuration_dependency_count||0} helper(s) hors SPOF externe</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v083(html):
    enhanced = _original_enhance_ui(html)
    if not isinstance(enhanced, str):
        return enhanced
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "Hardening 0.8.3" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V083 + "\n" + marker, 1)
    return enhanced


calibrated.hardened.runtime.enhance_ui_v080 = enhance_ui_v083


def compact_report_v083(report):
    payload = _original_compact(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "score_v5_preview",
        "consistency_analysis",
        "flow_confidence",
        "condition_semantics",
        "resilience_analysis",
        "root_cause_summary",
        "temporal_analysis",
    ):
        payload[key] = report.get(key) or {}
    return payload


def insights_report_v083(report):
    payload = _original_insights(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "score_v5_preview",
        "consistency_analysis",
        "flow_confidence",
        "condition_semantics",
        "resilience_analysis",
        "root_cause_summary",
        "temporal_analysis",
        "quality_gates",
    ):
        payload[key] = report.get(key) or {}
    return payload


calibrated.hardened.runtime.legacy.compact_report = compact_report_v083
calibrated.hardened.runtime.legacy.insights_report = insights_report_v083


class Handler(calibrated.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/hardening-v3") or path == "/api/hardening-v3":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "version": VERSION,
                "score_v5_preview": report.get("score_v5_preview") or {},
                "temporal_analysis": report.get("temporal_analysis") or {},
                "root_cause_summary": report.get("root_cause_summary") or {},
                "flow_confidence": report.get("flow_confidence") or {},
                "condition_semantics": report.get("condition_semantics") or {},
                "resilience_analysis": report.get("resilience_analysis") or {},
                "consistency_analysis": report.get("consistency_analysis") or {},
                "quality_gates": report.get("quality_gates") or {},
            })
        return super().do_GET()


if __name__ == "__main__":
    print(f"[HA Doctor] process started ({VERSION})", flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START", "true").lower() in {"1", "true", "yes", "on"}:
        def initial_scan():
            try:
                calibrated.hardened.runtime.legacy.run_scan()
                print("[HA Doctor] initial scan complete", flush=True)
            except Exception as exc:
                print(
                    f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )

        threading.Thread(target=initial_scan, daemon=True).start()

    print(
        f"[HA Doctor] web server listening on {calibrated.hardened.runtime.legacy.PORT}",
        flush=True,
    )
    calibrated.hardened.runtime.legacy.ThreadingHTTPServer(
        ("0.0.0.0", calibrated.hardened.runtime.legacy.PORT), Handler
    ).serve_forever()
