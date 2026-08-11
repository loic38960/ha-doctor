"""HA Doctor 0.13 Decision Engine runtime."""

import json
import os
import threading
from urllib.parse import urlparse

import app_v120 as previous
from contracts_v130 import VERSION, REPORT_SCHEMA, SHARE_SCHEMA, HISTORY_CONTRACT, DECISION_MODEL, CONDITION_MODEL
from scanner_v130 import scan as scan_v130
from sharing_v130 import MODEL as SHARE_MODEL, build_markdown_summary, build_share_report

previous.VERSION = VERSION
previous.REPORT_SCHEMA = REPORT_SCHEMA
_runtime = previous._runtime
_runtime.VERSION = VERSION
_runtime.scan = scan_v130
_original_enhance = previous.enhance_ui_v120

UI_PATCH_V130 = r"""
(function(){
  const renderOverviewLegacy130=renderOverview;
  renderOverview=function(r){
    renderOverviewLegacy130(r);
    const d=r.decision_engine||{},a=d.entity_attention||{},sem=r.condition_semantics||{},ctrl=r.controller_review_summary||{};
    const target=$('#view-overview'); if(!target) return;
    target.insertAdjacentHTML('afterbegin',`
      <div class="sectionHead" style="margin-top:0"><div><h2>HA Doctor 0.13 · Decision Engine</h2><p>Le diagnostic est maintenant transformé en décisions opérationnelles et playbooks manuels, sans modifier Home Assistant.</p></div>${badge((r.self_check||{}).status||'—',(r.self_check||{}).status==='pass'?'pass':'warn')}</div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="card"><div class="muted">Prêtes à corriger</div><div class="miniBig">${d.ready_for_manual_change_count??0}</div><div class="rootText">diagnostic(s) avec preuve suffisante et playbook manuel.</div></div>
        <div class="card"><div class="muted">Revue logique</div><div class="miniBig">${d.needs_logic_review_count??0}</div><div class="rootText">cas où HA Doctor refuse de deviner l'intention.</div></div>
        <div class="card"><div class="muted">Dépendances externes</div><div class="miniBig">${d.external_dependency_count??0}</div><div class="rootText">à restaurer ou confirmer hors ligne volontairement.</div></div>
      </div>
      <div class="grid grid3" style="margin-bottom:12px">
        <div class="miniCard"><div class="miniBig">${sem.mandatory_guard_resolved_pair_count??0}</div><div class="muted">paire(s) résolue(s) par garde obligatoire</div></div>
        <div class="miniCard"><div class="miniBig">${ctrl.physical_pair_count??0}</div><div class="muted">paire(s) physique(s) encore à revoir</div></div>
        <div class="miniCard"><div class="miniBig">${a.registry_actions_without_automation_impact??0}</div><div class="muted">incident(s) registre sans impact automation</div></div>
      </div>
      <div class="card"><div class="muted">Politique de décision</div><div class="rootText">Preuve → impact opérationnel → préparation de la réparation. Les compteurs unavailable/unknown bruts ne dictent jamais seuls la priorité.</div></div>`);
  };
})();
"""


def enhance_ui_v130(html):
    enhanced = _original_enhance(html)
    if not isinstance(enhanced, str):
        return enhanced
    enhanced = enhanced.replace("Le contrôle technique de votre Home Assistant · Temporal Truth Engine", "Le contrôle technique de votre Home Assistant · Decision Engine")
    marker = "refreshStatus();loadReport();startPolling();"
    if marker in enhanced and "HA Doctor 0.13 · Decision Engine" not in enhanced:
        enhanced = enhanced.replace(marker, UI_PATCH_V130 + "\n" + marker, 1)
    return enhanced

_runtime.enhance_ui_v080 = enhance_ui_v130


class Handler(previous.Handler):
    server_version = f"HADoctor/{VERSION}"

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/api/version") or path == "/api/version":
            return self._json({
                "product": "HA Doctor", "version": VERSION, "report_schema": REPORT_SCHEMA,
                "share_schema": SHARE_SCHEMA, "history_contract": HISTORY_CONTRACT,
                "decision_model": DECISION_MODEL, "condition_model": CONDITION_MODEL,
                "read_only": True, "automatic_fix": False, "decision_engine": True,
            })
        if path.endswith("/api/decision-engine") or path == "/api/decision-engine":
            report = self._report_or_404()
            if report is None: return
            return self._json({
                "version": VERSION,
                "decision_engine": report.get("decision_engine") or {},
                "controller_review_summary": report.get("controller_review_summary") or {},
                "condition_semantics": report.get("condition_semantics") or {},
                "entity_attention": (report.get("product_intelligence") or {}).get("entity_attention") or {},
            })
        if path.endswith("/api/repair-playbooks") or path == "/api/repair-playbooks":
            report = self._report_or_404()
            if report is None: return
            items = []
            for item in (report.get("decision_engine") or {}).get("items") or []:
                if isinstance(item, dict):
                    items.append({
                        "id": item.get("id"), "title": item.get("title"),
                        "operational_relevance": item.get("operational_relevance"),
                        "repair_playbook": item.get("repair_playbook") or {},
                    })
            return self._json({"version": VERSION, "automatic_fix": False, "read_only": True, "items": items})
        if path.endswith("/api/share-report") or path == "/api/share-report":
            report = self._report_or_404()
            if report is None: return
            return self._json(build_share_report(report))
        if path.endswith("/api/download-share") or path == "/api/download-share":
            report = self._report_or_404()
            if report is None: return
            payload = build_share_report(report)
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            meta = payload.get("export_meta") or {}
            return self._bytes(data, "application/json; charset=utf-8", headers={
                "Content-Disposition": 'attachment; filename="ha-doctor-support.json"',
                "X-HA-Doctor-Share-Bytes": str(len(data)), "X-HA-Doctor-Share-Model": SHARE_MODEL,
                "X-HA-Doctor-Decision-Model": DECISION_MODEL,
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
