"""HA Doctor 0.8.4 runtime wrapper."""
import os
import threading
from urllib.parse import urlparse

import app_v083 as previous
from scanner_v084 import scan as scan_v084

VERSION = "0.8.4"
REPORT_SCHEMA = "ha-doctor-report/0.8.4"

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
previous.calibrated.VERSION = VERSION
previous.calibrated.REPORT_SCHEMA = REPORT_SCHEMA
previous.calibrated.hardened.VERSION = VERSION
previous.calibrated.hardened.REPORT_SCHEMA = REPORT_SCHEMA
previous.calibrated.hardened.runtime.VERSION = VERSION
previous.calibrated.hardened.runtime.REPORT_SCHEMA = REPORT_SCHEMA
previous.calibrated.hardened.runtime.legacy.VERSION = VERSION
previous.calibrated.hardened.runtime.legacy.scan = scan_v084

_original_compact = previous.calibrated.hardened.runtime.legacy.compact_report
_original_insights = previous.calibrated.hardened.runtime.legacy.insights_report
_original_enhance = previous.enhance_ui_v083

UI_PATCH_V084 = r"""
(function(){
  const renderOverviewLegacy084=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy084(r);
    const l=r.entity_lineage||{},s=r.condition_semantics||{},t=r.temporal_analysis||{},root=r.root_cause_summary||{},rr=r.resilience_recommendations||{};
    const target=$('#view-overview');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Semantic Lineage 0.8.4</h2><p>Relations indirectes entre capteurs, templates, contrôleurs et automatisations.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${l.confirmed_edge_count||0}</div><div class="muted">relations de lineage confirmées</div></div>
        <div class="miniCard"><div class="miniBig">${root.registry_impacted_automation_count||0}</div><div class="muted">automatisation(s) touchée(s) par les incidents registry</div></div>
        <div class="miniCard"><div class="miniBig">${s.protocol_coordinated_pair_count||0}</div><div class="muted">handoff(s) de contrôleurs reconnu(s)</div></div>
      </div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${t.resolved_since_previous_count||0}</div><div class="muted">réellement résolu(s)</div></div>
        <div class="miniCard"><div class="miniBig">${t.deescalated_since_previous_count||0}</div><div class="muted">déclassé(s), toujours détecté(s)</div></div>
        <div class="miniCard"><div class="miniBig">${rr.count||0}</div><div class="muted">dépendance(s) de résilience priorisée(s)</div></div>
      </div>`);
  };

  const renderQualityLegacy084=renderQuality;
  renderQuality=function(r){
    renderQualityLegacy084(r);
    const l=r.entity_lineage||{},c=r.consistency_analysis||{},m=r.dependency_graph_meta||{},f=r.flow_confidence||{};
    const target=$('#view-quality');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Validation 0.8.4</h2><p>Le rapport contrôle aussi sa propre cohérence après recalcul sémantique.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${l.parse_error_count||0}</div><div class="muted">erreur(s) lineage</div></div>
        <div class="miniCard"><div class="miniBig">${m.low_confidence_dynamic_edges||0}</div><div class="muted">flux dynamiques faible confiance · moteur ${f.model||'—'}</div></div>
        <div class="miniCard"><div class="miniBig">${c.failure_count||0}</div><div class="muted">incohérence(s) interne(s)</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v084(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str):
        return enhanced
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "Semantic Lineage 0.8.4" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V084 + "\n" + marker, 1)
    return enhanced


previous.calibrated.hardened.runtime.enhance_ui_v080 = enhance_ui_v084


def compact_report_v084(report):
    payload = _original_compact(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "entity_lineage", "flow_confidence", "condition_semantics",
        "resilience_analysis", "resilience_recommendations",
        "root_cause_summary", "temporal_analysis", "consistency_analysis",
        "quality_gates", "score_v5_preview",
    ):
        payload[key] = report.get(key) or {}
    return payload


def insights_report_v084(report):
    payload = _original_insights(report)
    if not isinstance(payload, dict):
        return payload
    for key in (
        "entity_lineage", "flow_confidence", "condition_semantics",
        "resilience_analysis", "resilience_recommendations",
        "root_cause_summary", "temporal_analysis", "consistency_analysis",
        "quality_gates", "score_v5_preview",
    ):
        payload[key] = report.get(key) or {}
    return payload


previous.calibrated.hardened.runtime.legacy.compact_report = compact_report_v084
previous.calibrated.hardened.runtime.legacy.insights_report = insights_report_v084


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/semantic-lineage") or path == "/api/semantic-lineage":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "version": VERSION,
                "entity_lineage": report.get("entity_lineage") or {},
                "root_cause_summary": report.get("root_cause_summary") or {},
                "condition_semantics": report.get("condition_semantics") or {},
                "resilience_recommendations": report.get("resilience_recommendations") or {},
                "temporal_analysis": report.get("temporal_analysis") or {},
                "consistency_analysis": report.get("consistency_analysis") or {},
                "quality_gates": report.get("quality_gates") or {},
            })
        return super().do_GET()


if __name__ == "__main__":
    runtime = previous.calibrated.hardened.runtime.legacy
    print(f"[HA Doctor] process started ({VERSION})", flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START", "true").lower() in {"1", "true", "yes", "on"}:
        def initial_scan():
            try:
                runtime.run_scan()
                print("[HA Doctor] initial scan complete", flush=True)
            except Exception as exc:
                print(f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}", flush=True)
        threading.Thread(target=initial_scan, daemon=True).start()

    print(f"[HA Doctor] web server listening on {runtime.PORT}", flush=True)
    runtime.ThreadingHTTPServer(("0.0.0.0", runtime.PORT), Handler).serve_forever()
