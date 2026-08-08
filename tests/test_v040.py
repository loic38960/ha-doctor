import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
sys.path.insert(0, str(APP))

import registry_analysis
import scanner_v040


class RegistryAnalysisTests(unittest.TestCase):
    def test_integration_device_clustering_and_orphans(self):
        states = [
            {"entity_id": "light.kitchen", "state": "unavailable"},
            {"entity_id": "switch.kitchen", "state": "unavailable"},
            {"entity_id": "sensor.kitchen_temp", "state": "21"},
            {"entity_id": "number.kitchen_setting", "state": "unknown"},
            {"entity_id": "automation.old_rule", "state": "unavailable"},
        ]
        payload = {
            "available": True,
            "errors": [],
            "entities": [
                {"entity_id": "light.kitchen", "platform": "hue", "device_id": "d1", "disabled_by": None},
                {"entity_id": "switch.kitchen", "platform": "hue", "device_id": "d1", "disabled_by": None},
                {"entity_id": "sensor.kitchen_temp", "platform": "hue", "device_id": "d1", "disabled_by": None},
                {"entity_id": "number.kitchen_setting", "platform": "hue", "device_id": "d1", "entity_category": "config", "disabled_by": None},
                {"entity_id": "automation.old_rule", "platform": "automation", "device_id": None, "disabled_by": None},
                {"entity_id": "script.ghost", "platform": "script", "device_id": None, "disabled_by": None},
                {"entity_id": "button.optional", "platform": "demo", "device_id": "d2", "disabled_by": None},
                {"entity_id": "sensor.disabled", "platform": "demo", "device_id": "d2", "disabled_by": "user"},
            ],
            "devices": [
                {"id": "d1", "name": "Kitchen bridge", "manufacturer": "Test", "model": "X1"},
                {"id": "d2", "name": "Optional device"},
            ],
        }

        result = registry_analysis.analyze_registry(states, payload)
        self.assertTrue(result["available"])
        self.assertEqual(result["entity_registry_count"], 7)
        self.assertEqual(result["orphan_analysis"]["candidate_count"], 2)
        self.assertEqual(result["orphan_analysis"]["high_confidence_count"], 1)

        hue = next(x for x in result["integration_health"]["groups"] if x["integration"] == "hue")
        self.assertEqual(hue["core_total"], 3)
        self.assertEqual(hue["core_affected"], 2)
        self.assertEqual(hue["optional_affected"], 1)
        self.assertEqual(hue["status"], "degraded")

        device = next(x for x in result["device_health"]["groups"] if x["name"] == "Kitchen bridge")
        self.assertEqual(device["status"], "degraded")
        self.assertEqual(device["core_affected"], 2)

    def test_display_registry_normalization(self):
        payload = {
            "entity_categories": {"0": "config", "1": "diagnostic"},
            "entities": [
                {"ei": "light.room", "pl": "hue", "di": "abc", "ec": 0},
                {"ei": "sensor.room", "pl": "hue"},
            ],
        }
        result = registry_analysis._normalize_display_entities(payload)
        self.assertEqual(result[0]["entity_id"], "light.room")
        self.assertEqual(result[0]["entity_category"], "config")
        self.assertEqual(result[1]["platform"], "hue")


class V040ScannerTests(unittest.TestCase):
    def test_registry_insights_do_not_change_score(self):
        base_report = {
            "version": "0.3.2",
            "scores": {"global": 86, "domains": {"configuration": 93}},
            "score_meta": {"model": "priority_v1.2", "legacy_global": 80},
            "findings": [],
            "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "diagnostic_summary": {"priority_counts": {"action_now": 0, "verify": 0, "optimize": 0, "info": 0}},
            "diagnostics": {},
            "privacy": {},
        }
        registry_result = {
            "available": True,
            "errors": [],
            "integration_health": {"total": 2, "affected": 1, "offline": 0, "groups": []},
            "device_health": {"total": 1, "affected": 0, "groups": []},
            "orphan_analysis": {
                "candidate_count": 1,
                "high_confidence_count": 1,
                "registry_only_count": 1,
                "candidates": [{"entity_id": "script.ghost", "platform": "script", "confidence": "high", "reason": "enabled_registry_entry_without_state"}],
            },
        }
        with patch.object(scanner_v040.v032, "scan", return_value=base_report), \
             patch.object(scanner_v040.base, "_safe_api_get", return_value=[]), \
             patch.object(scanner_v040, "fetch_registries", return_value={"available": True, "entities": [], "devices": [], "errors": []}), \
             patch.object(scanner_v040, "analyze_registry", return_value=registry_result):
            report = scanner_v040.scan()

        self.assertEqual(report["version"], "0.4.0")
        self.assertEqual(report["scores"]["global"], 86)
        self.assertFalse(report["score_meta"]["registry_scoring"])
        self.assertEqual(report["diagnostic_summary"]["priority_counts"]["verify"], 1)
        self.assertEqual(report["findings"][0]["rule_id"], "HD-REG-001")
        self.assertFalse(report["privacy"]["registry_raw_payload_persisted"])


if __name__ == "__main__":
    unittest.main()
