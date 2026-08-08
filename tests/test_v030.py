import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
sys.path.insert(0, str(APP))

import scanner_patch


class V030Tests(unittest.TestCase):
    def test_priority_mapping(self):
        self.assertEqual(scanner_patch._priority_for({"rule_id": "HD-AUTO-009", "severity": "high"}), "action_now")
        self.assertEqual(scanner_patch._priority_for({"rule_id": "HD-ENT-003", "severity": "medium"}), "verify")
        self.assertEqual(scanner_patch._priority_for({"rule_id": "HD-AUTO-001", "severity": "low"}), "optimize")
        self.assertEqual(scanner_patch._priority_for({"rule_id": "HD-CFG-005", "severity": "info"}), "info")

    def test_entity_health_groups_mobile_and_stateless(self):
        states = [
            {"entity_id": "sensor.iphone_test_ssid", "state": "unavailable"},
            {"entity_id": "sensor.iphone_test_bssid", "state": "unavailable"},
            {"entity_id": "switch.pompe", "state": "unavailable"},
            {"entity_id": "scene.salon", "state": "unknown"},
            {"entity_id": "button.restart", "state": "unknown"},
            {"entity_id": "number.arrosage_index", "state": "unknown"},
            {"entity_id": "sensor.temperature", "state": "unknown"},
        ]
        health = scanner_patch._entity_health(states)
        self.assertEqual(health["unavailable"]["total"], 3)
        self.assertEqual(health["unavailable"]["likely_transient_count"], 2)
        self.assertEqual(health["unavailable"]["attention_count"], 1)
        self.assertEqual(health["unknown"]["total"], 4)
        self.assertEqual(health["unknown"]["stateful_count"], 2)
        self.assertEqual(health["unknown"]["ignored_stateless_count"], 2)
        self.assertEqual(health["unknown"]["likely_optional_count"], 1)

    def test_reference_filter_uses_services_recorder_and_blueprints(self):
        actions = {"vacuum.locate"}
        recorder = {"sensor.time"}
        self.assertTrue(scanner_patch._technical_reference({"entity_id": "vacuum.locate", "locations": []}, actions, recorder))
        self.assertTrue(scanner_patch._technical_reference({"entity_id": "sensor.time", "locations": []}, actions, recorder))
        self.assertTrue(scanner_patch._technical_reference({"entity_id": "input_number.yaml", "locations": []}, actions, recorder))
        self.assertTrue(scanner_patch._technical_reference({
            "entity_id": "event.data",
            "locations": [{"file": "blueprints/script/example.yaml", "line": 1}],
        }, actions, recorder))
        self.assertFalse(scanner_patch._technical_reference({
            "entity_id": "sensor.reellement_absent",
            "locations": [{"file": "packages/test.yaml", "line": 3}],
        }, actions, recorder))

    def test_priority_score_is_less_harsh_than_legacy_penalties(self):
        findings = scanner_patch._decorate_findings([
            {"rule_id": "HD-AUTO-009", "severity": "high", "domain": "automations", "title": "A"},
            {"rule_id": "HD-AUTO-003", "severity": "medium", "domain": "automations", "title": "B"},
            {"rule_id": "HD-AUTO-001", "severity": "low", "domain": "automations", "title": "C"},
        ])
        scores = scanner_patch._build_priority_scores(findings)
        self.assertEqual(scores["domains"]["automations"], 81)
        self.assertGreater(scores["global"], 90)


if __name__ == "__main__":
    unittest.main()
