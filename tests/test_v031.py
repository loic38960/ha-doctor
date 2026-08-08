import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
sys.path.insert(0, str(APP))

import scanner_v031


class V031Tests(unittest.TestCase):
    def test_entity_health_refinement(self):
        health = {
            "unavailable": {
                "total": 10,
                "likely_transient_count": 4,
                "attention_count": 6,
                "groups": [
                    {"key": "mobile", "label": "Mobiles", "count": 4, "examples": []},
                    {"key": "device_settings", "label": "Paramètres", "count": 2, "examples": []},
                    {"key": "button", "label": "Button", "count": 1, "examples": []},
                    {"key": "sensors", "label": "Capteurs", "count": 3, "examples": []},
                ],
            },
            "unknown": {
                "total": 8,
                "stateful_count": 6,
                "ignored_stateless_count": 2,
                "likely_optional_count": 2,
                "attention_count": 4,
                "groups": [
                    {"key": "notify", "label": "Notify", "count": 1, "examples": []},
                    {"key": "device_settings", "label": "Paramètres", "count": 2, "examples": []},
                    {"key": "mobile", "label": "Mobiles", "count": 1, "examples": []},
                    {"key": "sensors", "label": "Capteurs", "count": 2, "examples": []},
                ],
            },
        }

        refined = scanner_v031._refine_entity_health(health)

        unavailable = refined["unavailable"]
        self.assertEqual(unavailable["likely_optional_count"], 3)
        self.assertEqual(unavailable["review_count"], 3)
        self.assertEqual(unavailable["attention_count"], 3)

        unknown = refined["unknown"]
        self.assertEqual(unknown["stateful_count"], 5)
        self.assertEqual(unknown["ignored_stateless_count"], 3)
        self.assertEqual(unknown["likely_optional_count"], 2)
        self.assertEqual(unknown["likely_transient_count"], 1)
        self.assertEqual(unknown["review_count"], 2)
        self.assertNotIn("notify", {group["key"] for group in unknown["groups"]})

    def test_sync_unknown_finding_summary(self):
        report = {
            "entity_health": {
                "unavailable": {},
                "unknown": {"stateful_count": 12, "ignored_stateless_count": 5},
            },
            "findings": [
                {
                    "rule_id": "HD-ENT-003",
                    "summary": "old",
                    "recommendation": "old",
                }
            ],
        }
        scanner_v031._sync_entity_finding_summaries(report)
        self.assertIn("12 entité(s) stateful", report["findings"][0]["summary"])
        self.assertIn("5 entité(s) stateless", report["findings"][0]["summary"])


if __name__ == "__main__":
    unittest.main()
