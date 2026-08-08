"""HA Doctor 0.8 runtime wrapper.

Keeps the stable 0.7 HTTP surface while injecting the 0.8 scanner, exposing
flow/coverage endpoints and progressively enhancing the existing Ingress UI.
No write endpoint to Home Assistant is introduced.
"""

import os
import threading
from urllib.parse import urlparse

import app as legacy
from scanner_v080 import scan as scan_v080

VERSION = "0.8.0"
REPORT_SCHEMA = "ha-doctor-report/0.8"

# Reuse the proven runtime, locks, report persistence and download endpoints.
legacy.VERSION = VERSION
legacy.scan = scan_v080

_original_compact_report = legacy.compact_report
_original_insights_report = legacy.insights_report
_original_history_summary = legacy.history_summary


UI_PATCH_JS = r"""
(function(){
  const pct080 = value => value == null ? '—' : `${Math.round(Number(value) * 100)}%`;

  function normalizeImpact080(item){
    if(!item || !item.dependency_impact) return;
    const dep=item.dependency_impact;
    if(dep.critical_automation_count == null && dep.high_risk_automation_count != null){
      dep.critical_automation_count=dep.high_risk_automation_count;
    }
    if(dep.critical_automations == null && dep.high_risk_automations != null){
      dep.critical_automations=dep.high_risk_automations;
    }
  }

  function normalizeReport080(r){
    (r?.action_plan?.items||[]).forEach(normalizeImpact080);
    (r?.action_plan?.top||[]).forEach(normalizeImpact080);
    (r?.recommendation_queue?.items||[]).forEach(normalizeImpact080);
    (r?.diagnostic_explanations||[]).forEach(normalizeImpact080);
  }

  const renderAllLegacy080=renderAll;
  renderAll=function(r){
    normalizeReport080(r);
    return renderAllLegacy080(r);
  };

  const renderOverviewLegacy080=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy080(r);
    const g=r.dependency_graph_meta||{},c=r.automation_coverage||{},a=r.architecture_analysis||{};
    const target=$('#view-overview');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Entity Flow V3</h2><p>Ce que HA Doctor comprend réellement dans les automatisations 0.8.</p></div>${badge(g.model||'entity_flow_v3','pass')}</div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${pct080(g.target_resolution_rate)}</div><div class="muted">cibles d'action comprises</div></div>
        <div class="miniCard"><div class="miniBig">${pct080(c.coverage_ratio)}</div><div class="muted">automatisations runtime couvertes</div></div>
        <div class="miniCard"><div class="miniBig">${g.unresolved_dynamic_target_count||0}</div><div class="muted">cible(s) dynamique(s) non résolue(s)</div></div>
      </div>`);
  };

  const renderArchitectureLegacy080=renderArchitecture;
  renderArchitecture=function(r){
    renderArchitectureLegacy080(r);
    const a=r.architecture_analysis||{},g=r.dependency_graph_meta||{},c=r.automation_coverage||{};
    const target=$('#view-architecture');
    if(!target) return;

    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>Entity Flow V3</h2><p>Résolution sémantique des commandes, appels et cibles dynamiques.</p></div>${badge(g.model||'entity_flow_v3','pass')}</div>
      <div class="grid grid3" style="margin-bottom:18px">
        <div class="card"><div class="rootHead"><strong>Cibles comprises</strong>${badge(pct080(g.target_resolution_rate),Number(g.target_resolution_rate||0)>=.92?'pass':'warn')}</div><div class="miniBig">${pct080(g.target_resolution_rate)}</div><div class="rootText">${g.resolved_target_attempts||0}/${g.target_attempts||0} tentative(s) de cible résolue(s).</div></div>
        <div class="card"><div class="rootHead"><strong>Cibles dynamiques</strong>${badge(pct080(g.dynamic_target_resolution_rate),Number(g.dynamic_target_resolution_rate||0)>=.85?'pass':'warn')}</div><div class="miniBig">${pct080(g.dynamic_target_resolution_rate)}</div><div class="rootText">${g.unresolved_dynamic_target_count||0} cible(s) restant non démontrable(s) statiquement.</div></div>
        <div class="card"><div class="rootHead"><strong>Couverture runtime</strong>${badge(pct080(c.coverage_ratio),Number(c.coverage_ratio||0)>=.95?'pass':'warn')}</div><div class="miniBig">${pct080(c.coverage_ratio)}</div><div class="rootText">${c.yaml_automations_analyzed||0}/${c.expected_analyzable_automations||0} automation(s) disponible(s) analysée(s) · ${c.runtime_unavailable_automations||0} unavailable séparée(s).</div></div>
        <div class="card"><div class="rootHead"><strong>Commandes</strong>${badge(String(g.control_edges||0))}</div><div class="miniBig">${g.control_edges||0}</div><div class="rootText">arête(s) de commande physique/helper après résolution.</div></div>
        <div class="card"><div class="rootHead"><strong>Appels</strong>${badge(String(g.call_edges||0))}</div><div class="miniBig">${g.call_edges||0}</div><div class="rootText">appel(s) script/scène/automation séparé(s) des commandes.</div></div>
        <div class="card"><div class="rootHead"><strong>Dépendances critiques</strong>${badge(String(a.critical_dependency_count||0),a.critical_dependency_count?'warn':'pass')}</div><div class="miniBig">${a.critical_dependency_count||0}</div><div class="rootText">capteur(s)/helper(s) très centraux dans la logique métier.</div></div>
      </div>`);

    const calls=a.call_hubs||[],deps=a.critical_dependencies||[];
    if(calls.length || deps.length){
      target.insertAdjacentHTML('beforeend',`
        <div class="sectionHead"><div><h2>Flux partagés</h2><p>Hubs d'appel et dépendances dont la perte peut toucher plusieurs automatisations.</p></div></div>
        <div class="grid grid2">
          <div class="card"><strong>Call hubs</strong><div class="grid" style="margin-top:10px">${calls.slice(0,8).map(x=>`<div class="miniCard"><div class="rootHead"><strong>${esc(x.entity_id)}</strong>${badge(String(x.calling_automations||0))}</div><div class="muted">${x.calling_automations||0} appelant(s) · criticité ${x.criticality||0}/100</div></div>`).join('')||'<div class="muted">Aucun hub d’appel majeur.</div>'}</div></div>
          <div class="card"><strong>Dépendances critiques</strong><div class="grid" style="margin-top:10px">${deps.slice(0,8).map(x=>`<div class="miniCard"><div class="rootHead"><strong>${esc(x.entity_id)}</strong>${badge(String(x.criticality||0))}</div><div class="muted">${x.triggered_automations||0} trigger(s) · ${x.referencing_automations||0} référence(s)</div></div>`).join('')||'<div class="muted">Aucune dépendance critique détectée.</div>'}</div></div>
        </div>`);
    }
  };

  const renderQualityLegacy080=renderQuality;
  renderQuality=function(r){
    renderQualityLegacy080(r);
    const m=r.maintenance_debt||{},c=r.automation_coverage||{},g=r.dependency_graph_meta||{};
    const target=$('#view-quality');
    if(!target) return;
    target.insertAdjacentHTML('beforeend',`
      <div class="sectionHead"><div><h2>Contrôles 0.8</h2><p>Les signaux faibles, la couverture et les flux dynamiques sont mesurés séparément.</p></div></div>
      <div class="grid grid3">
        <div class="miniCard"><div class="miniBig">${m.probable_orphan_count||0}</div><div class="muted">orphelin(s) probable(s)</div></div>
        <div class="miniCard"><div class="miniBig">${m.stale_registry_automation_candidates||0}</div><div class="muted">ancienne(s) automation(s) registry à revoir</div></div>
        <div class="miniCard"><div class="miniBig">${c.coverage_gap||0}</div><div class="muted">vrai écart de couverture</div></div>
        <div class="miniCard"><div class="miniBig">${g.call_edges||0}</div><div class="muted">appel(s) séparé(s) des commandes</div></div>
        <div class="miniCard"><div class="miniBig">${g.possible_control_edges||0}</div><div class="muted">commande(s) dynamique(s) à confiance réduite</div></div>
        <div class="miniCard"><div class="miniBig">${m.double_count_protection?'Oui':'Non'}</div><div class="muted">protection contre double comptage</div></div>
      </div>`);
  };
})();
"""


def enhance_ui_v080(html):
    """Inject 0.8 UI metrics while keeping the stable 0.7 static bundle intact."""
    if not isinstance(html, str):
        return html
    html = html.replace("__HA_DOCTOR_VERSION__", VERSION)
    html = html.replace(
        "HA Doctor 0.7 corrèle les causes racines, la persistance et le blast radius des dépendances",
        "HA Doctor 0.8 corrèle les causes racines et comprend les flux dynamiques, appels et dépendances",
    )
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in html and "Entity Flow V3" not in html.split(marker, 1)[0][-6000:]:
        html = html.replace(marker, UI_PATCH_JS + "\n" + marker, 1)
    return html


def compact_report_v080(report):
    payload = _original_compact_report(report)
    if not isinstance(payload, dict):
        return payload
    for key in ("automation_coverage", "dependency_graph_meta"):
        if key in report:
            payload[key] = report[key]
    return payload


def insights_report_v080(report):
    payload = _original_insights_report(report)
    if not isinstance(payload, dict):
        return payload
    payload["automation_coverage"] = report.get("automation_coverage") or {}
    payload["dependency_graph_meta"] = report.get("dependency_graph_meta") or {}
    return payload


def history_summary_v080():
    payload = _original_history_summary()
    for source, item in zip(legacy.load_history(legacy.HISTORY_PATH), payload.get("items") or []):
        item["flow_target_resolution_rate"] = source.get("flow_target_resolution_rate")
        item["flow_dynamic_resolution_rate"] = source.get("flow_dynamic_resolution_rate")
        item["automation_coverage_ratio"] = source.get("automation_coverage_ratio")
        item["report_version"] = source.get("report_version")
    payload["version"] = VERSION
    return payload


legacy.compact_report = compact_report_v080
legacy.insights_report = insights_report_v080
legacy.history_summary = history_summary_v080


class Handler(legacy.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path

        if path in {"/", ""}:
            html = (legacy.STATIC_DIR / "index.html").read_text(encoding="utf-8")
            html = enhance_ui_v080(html)
            return self._bytes(html.encode("utf-8"), "text/html; charset=utf-8")

        if path.endswith("/api/version") or path == "/api/version":
            return self._json({
                "product": "HA Doctor",
                "version": VERSION,
                "report_schema": REPORT_SCHEMA,
                "read_only": True,
                "automatic_fix": False,
                "flow_model": "entity_flow_v3",
            })

        if path.endswith("/api/flow") or path == "/api/flow":
            report = self._report_or_404()
            if report is None:
                return
            graph = report.get("dependency_graph") or []
            unresolved = []
            for node in graph:
                issues = node.get("unresolved_dynamic_targets") or []
                if not issues:
                    continue
                unresolved.append({
                    "automation": node.get("automation"),
                    "source": node.get("source"),
                    "count": len(issues),
                    "targets": issues[:6],
                })
            return self._json({
                "dependency_graph_meta": report.get("dependency_graph_meta") or {},
                "automation_coverage": report.get("automation_coverage") or {},
                "architecture_summary": {
                    key: (report.get("architecture_analysis") or {}).get(key)
                    for key in (
                        "model",
                        "complexity_score",
                        "complexity_label",
                        "shared_actuator_count",
                        "critical_dependency_count",
                        "call_hub_count",
                        "closed_loop_count",
                    )
                },
                "unresolved_dynamic_targets": unresolved[:30],
                "privacy": {
                    "raw_yaml_included": False,
                    "template_text_included": False,
                    "secret_values_included": False,
                },
            })

        if path.endswith("/api/coverage") or path == "/api/coverage":
            report = self._report_or_404()
            if report is None:
                return
            return self._json({
                "automation_coverage": report.get("automation_coverage") or {},
                "maintenance_debt": report.get("maintenance_debt") or {},
            })

        return super().do_GET()


if __name__ == "__main__":
    print(f"[HA Doctor] process started ({VERSION})", flush=True)
    if os.getenv("HA_DOCTOR_SCAN_ON_START", "true").lower() in {"1", "true", "yes", "on"}:
        def initial_scan():
            try:
                legacy.run_scan()
                print("[HA Doctor] initial scan complete", flush=True)
            except Exception as exc:
                print(
                    f"[HA Doctor] initial scan failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )

        threading.Thread(target=initial_scan, daemon=True).start()

    print(f"[HA Doctor] web server listening on {legacy.PORT}", flush=True)
    legacy.ThreadingHTTPServer(("0.0.0.0", legacy.PORT), Handler).serve_forever()
