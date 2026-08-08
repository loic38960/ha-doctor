import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
sys.path.insert(0, str(APP))

import scanner_v032


class V032Tests(unittest.TestCase):
    def test_mobile_notify_unknown_is_stateless_before_grouping(self):
        v031 = scanner_v032.v031
        original_scan = v031.scan

        states = [
            {"entity_id": "notify.ipad_boulot", "state": "unknown"},
            {"entity_id": "notify.ipad_de_loic", "state": "unknown"},
            {"entity_id": "sensor.temperature_test", "state": "unknown"},
        ]

        def fake_scan(include_yaml=True):
            health = v031.v030._entity_health(states)
            return {
                "version": "0.3.1",
                "entity_health": v031._refine_entity_health(health),
                "findings": [],
                "score_meta": {"model": "priority_v1.1"},
            }

        v031.scan = fake_scan
        try:
            report = scanner_v032.scan(include_yaml=False)
        finally:
            v031.scan = original_scan

        unknown = report["entity_health"]["unknown"]
        self.assertEqual(report["version"], "0.3.2")
        self.assertEqual(report["score_meta"]["model"], "priority_v1.2")
        self.assertEqual(unknown["total"], 3)
        self.assertEqual(unknown["stateful_count"], 1)
        self.assertEqual(unknown["ignored_stateless_count"], 2)
        grouped_examples = [
            entity
            for group in unknown["groups"]
            for entity in group.get("examples", [])
        ]
        self.assertNotIn("notify.ipad_boulot", grouped_examples)
        self.assertNotIn("notify.ipad_de_loic", grouped_examples)

    def test_stateless_domain_set_is_restored_after_scan(self):
        v031 = scanner_v032.v031
        original_scan = v031.scan
        domains = v031.v030.STATELESS_UNKNOWN_DOMAINS
        notify_was_present = "notify" in domains

        def fake_scan(include_yaml=True):
            self.assertIn("notify", domains)
            return {"entity_health": {}, "findings": [], "score_meta": {}}

        v031.scan = fake_scan
        try:
            scanner_v032.scan(include_yaml=False)
        finally:
            v031.scan = original_scan

        self.assertEqual("notify" in domains, notify_was_present)


if __name__ == "__main__":
    unittest.main()
