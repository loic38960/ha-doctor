import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
sys.path.insert(0, str(APP))

import scanner


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name)
        fixtures = ROOT / "tests" / "fixtures"
        for f in fixtures.iterdir():
            (self.config / f.name).write_text(f.read_text(), encoding="utf-8")
        (self.config / "secrets.yaml").write_text("api_key: MUST_NEVER_BE_READ\n", encoding="utf-8")
        scanner.CONFIG_ROOT = self.config

    def tearDown(self):
        self.tmp.cleanup()

    def test_yaml_scan_excludes_secrets_and_detects_core_rules(self):
        result = scanner._scan_yaml({"switch.pompe_piscine", "sensor.surplus_pv"})
        self.assertEqual(result["files_scanned"], 2)
        self.assertEqual(len(result["automations"]), 2)
        self.assertEqual(len(result["potential_inline_secrets"]), 1)
        self.assertEqual(result["potential_inline_secrets"][0]["key"], "password")
        missing = {x["entity_id"] for x in result["missing_entity_references"]}
        self.assertIn("sensor.inexistant", missing)
        content = str(result)
        self.assertNotIn("MUST_NEVER_BE_READ", content)
        self.assertNotIn("super-secret-value", content)

    @patch("scanner._safe_api_get")
    def test_full_report_never_persists_raw_state_values(self, api):
        def fake(path, errors):
            if path == "/core/api/config":
                return {"version":"2026.8.0", "components": ["automation"]}
            if path == "/core/api/states":
                return [
                    {"entity_id":"switch.pompe_piscine","state":"on","attributes":{"friendly_name":"Pompe"}},
                    {"entity_id":"sensor.surplus_pv","state":"1234","attributes":{}},
                ]
            return {"result":"ok","data":{}}
        api.side_effect = fake
        report = scanner.scan(include_yaml=True)
        self.assertEqual(report["inventory"]["states"], 2)
        self.assertNotIn("states", report)
        self.assertTrue(report["privacy"]["raw_states_persisted"] is False)
        rules = {f["rule_id"] for f in report["findings"]}
        self.assertIn("HD-AUTO-003", rules)
        self.assertIn("HD-SEC-001", rules)


if __name__ == "__main__":
    unittest.main()
