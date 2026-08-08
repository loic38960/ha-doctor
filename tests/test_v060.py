import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from share_export import build_anonymized_report
from temporal_v060 import enrich_v060


class V060Tests(unittest.TestCase):
    def base_report(self):
        return {
            "product": "HA Doctor",
            "generated_at": "2026-08-08T20:00:00Z",
            "scores": {"global": 86, "domains": {}},
            "inventory": {"states": 100, "unavailable_count": 10, "unknown_count": 4},
            "dependency_graph": [
                {"automation": "Test automation", "references": ["sensor.device_power"], "triggers_on": ["sensor.device_power"], "controls": []}
            ],
            "registry_analysis": {
                "available": True,
                "orphan_analysis": {"probable_orphan_count": 0},
                "integration_health": {"groups": [{"integration": "demo_cloud", "examples": ["sensor.device_power"]}]},
                "device_health": {"groups": []},
            },
            "registry_observations": [],
            "diagnostic_explanations": [
                {
                    "id": "DX-HD-SEC-001", "source_type": "finding", "source_id": "HD-SEC-001", "rule_id": "HD-SEC-001",
                    "title": "Sensitive value", "priority": "action_now", "priority_label": "À corriger maintenant",
                    "severity": "high", "domain": "security", "confidence": "high", "confidence_label": "Élevée",
                    "confidence_score": 0.95, "checks": [], "evidence": []
                },
                {
                    "id": "DX-REG-INT-demo_cloud", "source_type": "registry_integration", "source_id": "demo_cloud",
                    "title": "demo_cloud indisponible", "priority": "verify", "priority_label": "À vérifier",
                    "severity": "medium", "domain": "entities", "confidence": "high", "confidence_label": "Élevée",
                    "confidence_score": 0.92, "checks": [], "evidence": []
                },
                {
                    "id": "DX-HD-ENT-001", "source_type": "finding", "source_id": "HD-ENT-001", "rule_id": "HD-ENT-001",
                    "title": "Unavailable", "priority": "verify", "priority_label": "À vérifier",
                    "severity": "medium", "domain": "entities", "confidence": "medium", "confidence_label": "Moyenne",
                    "confidence_score": 0.68, "checks": [], "evidence": []
                },
            ],
            "findings": [],
        }

    def test_root_cause_suppresses_generic_entity_noise(self):
        with tempfile.TemporaryDirectory() as d:
            report = enrich_v060(self.base_report(), str(Path(d) / "history.json"))
            ids = [x["id"] for x in report["action_plan"]["items"]]
            self.assertNotIn("DX-HD-ENT-001", ids)
            self.assertIn("DX-REG-INT-demo_cloud", ids)
            self.assertEqual(report["action_plan"]["remaining"], 0)

    def test_history_marks_persistence_and_score_delta(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "history.json")
            first = enrich_v060(self.base_report(), path)
            second_report = self.base_report()
            second_report["generated_at"] = "2026-08-08T21:00:00Z"
            second = enrich_v060(second_report, path)
            incident = next(x for x in second["diagnostic_explanations"] if x["id"] == "DX-REG-INT-demo_cloud")
            self.assertEqual(incident["temporal"]["status"], "persistent")
            self.assertEqual(incident["temporal"]["consecutive_scans"], 2)
            self.assertEqual(second["temporal_analysis"]["scan_count"], 2)
            self.assertIsNotNone(second["temporal_analysis"]["previous_score"])
            self.assertEqual(first["privacy"]["temporal_history_raw_states_persisted"], False)

    def test_dependency_impact_is_attached(self):
        with tempfile.TemporaryDirectory() as d:
            report = enrich_v060(self.base_report(), str(Path(d) / "history.json"))
            incident = next(x for x in report["diagnostic_explanations"] if x["id"] == "DX-REG-INT-demo_cloud")
            self.assertEqual(incident["dependency_impact"]["impacted_automation_count"], 1)
            self.assertEqual(incident["dependency_impact"]["level"], "medium")

    def test_anonymized_export_removes_local_identifiers(self):
        report = self.base_report()
        report["version"] = "0.6.0"
        report["action_plan"] = {
            "total": 1,
            "counts": {"verify": 1},
            "items": [{
                "title": "Private device", "priority": "verify", "severity": "medium", "domain": "entities",
                "confidence": "high", "source_type": "registry_device", "source_id": "Private device",
                "dependency_impact": {"level": "medium"},
            }],
        }
        export = build_anonymized_report(report)
        text = str(export)
        self.assertNotIn("Private device", text)
        self.assertFalse(export["privacy"]["entity_ids_included"])
        self.assertTrue(export["export_meta"]["identifiers_removed"])


if __name__ == "__main__":
    unittest.main()
