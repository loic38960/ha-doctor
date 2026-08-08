import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
sys.path.insert(0, str(APP))

import app


class CompactExportTests(unittest.TestCase):
    def test_compact_export_excludes_dependency_graph_and_raw_findings(self):
        report = {
            "product": "HA Doctor",
            "version": "0.7.0",
            "generated_at": "2026-08-08T20:00:00Z",
            "scores": {"global": 86},
            "privacy": {"raw_states_persisted": False},
            "inventory": {
                "states": 1800,
                "automations_detected": 50,
                "blueprints_detected": 12,
                "yaml_files_scanned": 300,
                "unavailable_count": 100,
                "unknown_count": 80,
            },
            "executive_summary": {"text": "Synthèse"},
            "action_plan": {"items": [{"title": "Action"}]},
            "architecture_analysis": {"complexity_score": 63},
            "maintenance_debt": {"score": 22},
            "quality_gates": {"overall": "pass"},
            "regression_analysis": {"state": "stable"},
            "report_schema": {"version": "ha-doctor-report/0.7"},
            "registry_analysis": {
                "available": True,
                "entity_registry_count": 1700,
                "device_registry_count": 170,
                "integration_health": {
                    "total": 10,
                    "affected": 2,
                    "problematic": 1,
                    "offline": 1,
                    "groups": [
                        {"integration": "bad", "status": "offline"},
                        {"integration": "good", "status": "healthy"},
                    ],
                },
                "device_health": {
                    "total": 20,
                    "affected": 1,
                    "problematic": 1,
                    "offline": 1,
                    "groups": [{"name": "Device", "status": "offline"}],
                },
                "orphan_analysis": {
                    "probable_orphan_count": 1,
                    "review_candidate_count": 2,
                    "probable_orphans": [{"entity_id": "script.ghost"}],
                    "local_unavailable_candidates": [{"entity_id": "automation.old"}],
                },
            },
            "dependency_graph": [{"very": "large"}],
            "findings": [{"examples": [{"huge": "blob"}]}],
            "diagnostic_explanations": [{"title": "Very detailed diagnostic"}],
        }

        compact = app.compact_report(report)
        self.assertEqual(compact["scores"]["global"], 86)
        self.assertIn("action_plan", compact)
        self.assertIn("architecture_analysis", compact)
        self.assertIn("maintenance_debt", compact)
        self.assertIn("quality_gates", compact)
        self.assertIn("report_schema", compact)
        self.assertNotIn("dependency_graph", compact)
        self.assertNotIn("findings", compact)
        self.assertNotIn("diagnostic_explanations", compact)
        self.assertTrue(compact["export_meta"]["intended_for_sharing"])
        groups = compact["registry_summary"]["integration_health"]["groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["integration"], "bad")

    def test_compact_export_is_none_for_invalid_input(self):
        self.assertIsNone(app.compact_report(None))

    def test_version_endpoint_contract_constants(self):
        self.assertEqual(app.VERSION, "0.7.0")
        self.assertTrue(app.scan_status()["read_only"])
        self.assertFalse(app.scan_status()["automatic_fix"])


if __name__ == "__main__":
    unittest.main()
