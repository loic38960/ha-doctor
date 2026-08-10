import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from sharing_v086 import build_share_report


class V086Tests(unittest.TestCase):
    def _report(self):
        return {
            "product": "HA Doctor",
            "version": "0.8.6",
            "generated_at": "2026-08-10T11:00:00Z",
            "scores": {"global": 76, "domains": {"automations": 75}},
            "severity_counts": {"high": 2},
            "home_assistant": {"version": "2026.8.1", "time_zone": "Europe/Paris", "components_count": 382},
            "inventory": {
                "states": 1866,
                "unavailable_count": 215,
                "unknown_count": 153,
                "yaml_files_scanned": 324,
                "automations_detected": 52,
                "blueprints_detected": 12,
                "entity_references_detected": 422,
            },
            "findings": [{
                "rule_id": "HD-AUTO-009",
                "title": "Double writer",
                "severity": "high",
                "domain": "automations",
                "summary": "Two writers",
                "recommendation": "Check writers",
                "priority": "action_now",
                "examples": [{
                    "entity_id": "input_number.vb_energy_kwh",
                    "affected_entities": [f"sensor.big_{i}" for i in range(500)],
                }],
            }],
            "action_plan": {
                "model": "plan",
                "total": 1,
                "counts": {"action_now": 1, "verify": 0, "optimize": 0},
                "items": [{
                    "id": "DX-HD-AUTO-009",
                    "title": "Double writer",
                    "priority": "action_now",
                    "severity": "high",
                    "domain": "automations",
                    "diagnosis": "Two automations write the same helper",
                    "first_check": {"step": 1, "title": "Open YAML", "detail": "Compare both writers"},
                    "temporal": {"status": "persistent", "occurrences": 12, "first_seen": "2026-08-08T00:00:00Z"},
                    "dependency_impact": {
                        "level": "low",
                        "impacted_automation_count": 0,
                        "impacted_automations": [f"Automation {i}" for i in range(100)],
                    },
                }],
            },
            "diagnostic_explanations": [{
                "id": "DX-INFO",
                "title": "Seasonal heater",
                "priority": "info",
                "source_type": "registry_cluster",
                "diagnosis": "Heating may be intentionally off",
            }],
            "entity_health": {
                "unavailable": {"total": 215, "groups": [{"key": "mobile", "label": "Mobile", "count": 46, "examples": ["sensor.phone"]}]},
                "unknown": {"total": 153, "groups": []},
            },
            "registry_analysis": {
                "available": True,
                "entity_registry_count": 1791,
                "device_registry_count": 181,
                "integration_health": {
                    "total": 52,
                    "affected": 20,
                    "offline": 2,
                    "problematic": 7,
                    "groups": [{
                        "integration": "huawei_solar",
                        "status": "offline",
                        "core_total": 16,
                        "core_affected": 16,
                        "examples": ["sensor.onduleur_puissance_active"],
                        "affected_entities": [f"sensor.inverter_{i}" for i in range(1000)],
                    }],
                },
                "device_health": {"total": 181, "affected": 30, "offline": 6, "problematic": 9, "groups": []},
                "orphan_analysis": {"candidate_count": 29, "high_confidence_count": 0},
            },
            "dependency_graph": [
                {
                    "automation": f"Automation {i}",
                    "references": [f"sensor.entity_{j}" for j in range(400)],
                    "reads": [f"sensor.entity_{j}" for j in range(400)],
                }
                for i in range(80)
            ],
            "architecture_analysis": {
                "model": "architecture_v3_post_flow",
                "complexity_score": 61,
                "shared_actuator_count": 14,
                "critical_dependency_count": 4,
                "closed_loop_count": 3,
                "post_flow_recomputed": True,
                "top_hotspots": [{"entity_id": "switch.pompe_piscine", "score": 100, "controllers": [f"A{i}" for i in range(50)]}],
            },
            "condition_semantics": {
                "model": "condition_semantics_v5_branch_protocols",
                "resolved_pair_count": 2,
                "unproven_pair_count": 4,
                "physical_unproven_pair_count": 4,
                "branch_protocol_resolved_pair_count": 2,
                "unproven_pairs": [{"entity_id": "switch.pompe_piscine", "automations": ["A", "B"]}],
            },
            "flow_confidence": {"model": "flow_confidence_v3.1", "review_required_dynamic_edges": 0},
            "entity_lineage": {"model": "entity_lineage_v1", "confirmed_edge_count": 4, "edges": [{"source": f"sensor.{i}"} for i in range(1000)]},
            "resilience_analysis": {"model": "resilience_spof_v3", "critical_dependency_count": 4, "items": []},
            "score_meta": {"model": "root_cause_temporal_v4_flow_v3_hardened", "penalty_total": 24, "penalty_breakdown": []},
            "quality_gates": {"overall": "pass", "gates": []},
            "consistency_analysis": {"status": "pass", "failure_count": 0},
            "report_schema": {"version": "ha-doctor-report/0.8.6", "capabilities": ["assistant_share_report_v1"]},
        }

    def test_version_modules(self):
        import app_v086
        import scanner_v086
        import sharing_v086
        self.assertEqual(app_v086.VERSION, "0.8.6")
        self.assertEqual(scanner_v086.VERSION, "0.8.6")
        self.assertEqual(sharing_v086.VERSION, "0.8.6")

    def test_share_report_excludes_full_graph_and_preserves_diagnostic_identity(self):
        payload = build_share_report(self._report())
        self.assertNotIn("dependency_graph", payload)
        self.assertNotIn("diagnostic_explanations", payload)
        self.assertEqual(payload["findings"][0]["rule_id"], "HD-AUTO-009")
        self.assertEqual(payload["action_plan"]["items"][0]["id"], "DX-HD-AUTO-009")
        self.assertEqual(payload["non_plan_observations"][0]["id"], "DX-INFO")
        self.assertEqual(payload["registry_summary"]["integration_health"]["groups"][0]["integration"], "huawei_solar")

    def test_heavy_lists_are_bounded(self):
        payload = build_share_report(self._report())
        example = payload["findings"][0]["examples"][0]
        self.assertEqual(example["affected_entities_count"], 500)
        self.assertLessEqual(len(example["affected_entities_examples"]), 4)
        registry = payload["registry_summary"]["integration_health"]["groups"][0]
        self.assertNotIn("affected_entities", registry)

    def test_share_report_is_materially_smaller_than_full_report(self):
        report = self._report()
        full = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        payload = build_share_report(report)
        shared = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLess(len(shared), len(full) * 0.35)
        self.assertFalse(payload["export_meta"]["full_dependency_graph_included"])
        self.assertTrue(payload["export_meta"]["entity_ids_preserved"])

    def test_ui_injects_share_button(self):
        import app_v086
        source = (APP / "static" / "index.html").read_text(encoding="utf-8")
        enhanced = app_v086.enhance_ui_v086(source)
        self.assertIn("Rapport à envoyer", enhanced)
        self.assertIn("download-share", enhanced)
        self.assertIn("Partage 0.8.6", enhanced)


if __name__ == "__main__":
    unittest.main()
