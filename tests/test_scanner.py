import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
sys.path.insert(0, str(APP))

import scanner
from rules import evaluate


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name)
        fixtures = ROOT / "tests" / "fixtures"
        for item in fixtures.iterdir():
            dest = self.config / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                dest.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
        (self.config / "secrets.yaml").write_text("api_key: MUST_NEVER_BE_READ\n", encoding="utf-8")
        scanner.CONFIG_ROOT = self.config

    def tearDown(self):
        self.tmp.cleanup()

    def test_yaml_scan_excludes_secrets_and_resolves_blueprints(self):
        live = {
            "switch.pompe_piscine",
            "switch.pompe_blueprint",
            "sensor.surplus_pv",
            "input_select.mode_test",
        }
        result = scanner._scan_yaml(live)
        self.assertEqual(result["blueprints_detected"], 1)
        self.assertEqual(len(result["automations"]), 4)
        self.assertEqual(len(result["potential_inline_secrets"]), 1)
        self.assertEqual(result["potential_inline_secrets"][0]["key"], "password")

        mode_a = next(a for a in result["automations"] if a["id"] == "mode_a")
        self.assertTrue(mode_a["blueprint_resolved"])
        self.assertEqual(mode_a["controlled_entities"], ["switch.pompe_blueprint"])
        self.assertEqual(mode_a["state_guards"]["input_select.mode_test"], ["A"])

        missing = {x["entity_id"] for x in result["missing_entity_references"]}
        self.assertIn("sensor.inexistant", missing)
        self.assertNotIn("sensor.blueprint_default_unused", missing)
        self.assertNotIn("switch.blueprint_default_unused", missing)

        content = str(result)
        self.assertNotIn("MUST_NEVER_BE_READ", content)
        self.assertNotIn("super-secret-value", content)

    def test_duplicate_actions_and_mutual_exclusion(self):
        live = {
            "switch.pompe_piscine",
            "switch.pompe_blueprint",
            "sensor.surplus_pv",
            "input_select.mode_test",
        }
        yaml_result = scanner._scan_yaml(live)
        snapshot = {"states": [], "yaml": yaml_result, "api_errors": []}
        findings = evaluate(snapshot)
        by_rule = {f["rule_id"]: f for f in findings}

        self.assertIn("HD-AUTO-005", by_rule)
        duplicate_examples = by_rule["HD-AUTO-005"]["examples"]
        self.assertTrue(any(x["alias"] == "Pompe piscine matin" for x in duplicate_examples))

        # The two blueprint modes both control the same pump but are protected by
        # mutually-exclusive top-level state conditions. They must not appear as a conflict.
        conflicts = by_rule["HD-AUTO-003"]["examples"]
        conflict_entities = {x["entity_id"] for x in conflicts}
        self.assertIn("switch.pompe_piscine", conflict_entities)
        self.assertNotIn("switch.pompe_blueprint", conflict_entities)

    def test_duplicate_ids_are_high_severity(self):
        snapshot = {
            "states": [],
            "api_errors": [],
            "yaml": {
                "automations": [
                    {"id": "same", "alias": "A", "source": "a.yaml", "controlled_entities": []},
                    {"id": "same", "alias": "B", "source": "b.yaml", "controlled_entities": []},
                ],
                "missing_entity_references": [],
                "potential_inline_secrets": [],
                "unresolved_blueprints": [],
                "configuration": {},
                "parse_errors": [],
                "skipped_files": [],
            },
        }
        finding = next(f for f in evaluate(snapshot) if f["rule_id"] == "HD-AUTO-006")
        self.assertEqual(finding["severity"], "high")

    @patch("scanner._safe_api_get")
    def test_full_report_never_persists_raw_state_values(self, api):
        def fake(path, errors):
            if path == "/core/api/config":
                return {"version": "2026.8.0", "components": ["automation"]}
            if path == "/core/api/states":
                return [
                    {"entity_id": "switch.pompe_piscine", "state": "on", "attributes": {"friendly_name": "Pompe"}},
                    {"entity_id": "switch.pompe_blueprint", "state": "off", "attributes": {}},
                    {"entity_id": "sensor.surplus_pv", "state": "1234", "attributes": {}},
                    {"entity_id": "input_select.mode_test", "state": "A", "attributes": {}},
                ]
            return {"result": "ok", "data": {}}

        api.side_effect = fake
        report = scanner.scan(include_yaml=True)
        self.assertEqual(report["version"], "0.2.0")
        self.assertEqual(report["inventory"]["states"], 4)
        self.assertEqual(report["inventory"]["blueprints_detected"], 1)
        self.assertNotIn("states", report)
        self.assertTrue(report["privacy"]["raw_states_persisted"] is False)
        rules = {f["rule_id"] for f in report["findings"]}
        self.assertIn("HD-AUTO-003", rules)
        self.assertIn("HD-AUTO-005", rules)
        self.assertIn("HD-SEC-001", rules)


if __name__ == "__main__":
    unittest.main()
