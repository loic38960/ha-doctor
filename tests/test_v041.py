import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
sys.path.insert(0, str(APP))

import scanner_v041


class V041CalibrationTests(unittest.TestCase):
    def test_tesla_unknown_dominant_group_is_not_offline(self):
        item = {
            "integration": "tesla_fleet",
            "platforms": ["tesla_fleet"],
            "status": "offline",
            "missing_state": 0,
            "unknown": 47,
            "unavailable": 2,
        }
        result = scanner_v041._calibrate_group(item, "tesla_fleet")
        self.assertEqual(result["status"], "watch")
        self.assertTrue(result["transient_or_sleep_tolerant"])

    def test_mobile_app_degraded_is_downgraded_to_watch(self):
        item = {
            "platforms": ["mobile_app"],
            "status": "degraded",
            "missing_state": 0,
            "unknown": 1,
            "unavailable": 15,
        }
        result = scanner_v041._calibrate_group(item)
        self.assertEqual(result["status"], "watch")

    def test_medium_unavailable_candidates_are_not_probable_orphans(self):
        registry = {
            "orphan_analysis": {
                "candidate_count": 2,
                "high_confidence_count": 0,
                "candidates": [
                    {"entity_id": "automation.old", "confidence": "medium", "reason": "local_entity_unavailable_without_device"},
                    {"entity_id": "input_number.old", "confidence": "medium", "reason": "local_entity_unavailable_without_device"},
                ],
            }
        }
        result = scanner_v041._calibrate_orphans(registry)
        orphan = result["orphan_analysis"]
        self.assertEqual(orphan["probable_orphan_count"], 0)
        self.assertEqual(orphan["review_candidate_count"], 2)
        self.assertEqual(orphan["probable_orphans"], [])

    def test_registry_finding_uses_review_wording_without_high_confidence(self):
        report = {"findings": []}
        registry = {
            "orphan_analysis": {
                "probable_orphan_count": 0,
                "review_candidate_count": 1,
                "probable_orphans": [],
                "local_unavailable_candidates": [
                    {"entity_id": "automation.old", "confidence": "medium", "reason": "local_entity_unavailable_without_device"}
                ],
            }
        }
        scanner_v041._append_registry_findings(report, registry)
        self.assertEqual(len(report["findings"]), 1)
        self.assertEqual(report["findings"][0]["rule_id"], "HD-REG-002")
        self.assertNotIn("orphelines", report["findings"][0]["title"].lower())

    def test_scan_keeps_score_and_sets_041_version(self):
        base_report = {
            "version": "0.4.0",
            "scores": {"global": 86},
            "score_meta": {"model": "priority_v2-preview", "registry_scoring": False},
            "findings": [],
            "severity_counts": {},
            "diagnostic_summary": {},
            "registry_analysis": {
                "available": True,
                "integration_health": {
                    "total": 1,
                    "affected": 1,
                    "offline": 1,
                    "groups": [{
                        "integration": "tesla_fleet",
                        "platforms": ["tesla_fleet"],
                        "status": "offline",
                        "missing_state": 0,
                        "unknown": 20,
                        "unavailable": 1,
                    }],
                },
                "device_health": {"total": 0, "affected": 0, "groups": []},
                "orphan_analysis": {
                    "candidate_count": 0,
                    "high_confidence_count": 0,
                    "candidates": [],
                },
            },
        }
        with patch.object(scanner_v041.v040, "scan", return_value=base_report), \
             patch.object(scanner_v041.v040, "_resync_findings", side_effect=lambda report: None):
            report = scanner_v041.scan()

        self.assertEqual(report["version"], "0.4.1")
        self.assertEqual(report["scores"]["global"], 86)
        self.assertEqual(report["registry_analysis"]["integration_health"]["offline"], 0)
        self.assertEqual(report["registry_analysis"]["integration_health"]["groups"][0]["status"], "watch")
        self.assertEqual(report["score_meta"]["model"], "priority_v2.1-preview")


if __name__ == "__main__":
    unittest.main()
