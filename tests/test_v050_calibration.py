import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
sys.path.insert(0, str(APP))

import scanner_v050_calibration as calibration


class RootCauseCalibrationTests(unittest.TestCase):
    def test_local_logic_is_not_presented_as_integration_outage(self):
        report = {
            "scores": {"global": 86},
            "diagnostic_summary": {"priority_counts": {}},
            "registry_observations": [],
            "diagnostic_engine": {},
            "diagnostic_explanations": [
                {
                    "id": "DX-script",
                    "source_type": "registry_integration",
                    "source_id": "script",
                    "title": "script est partiellement dégradée",
                    "priority": "verify",
                    "severity": "low",
                    "confidence": "medium",
                    "confidence_score": 0.7,
                    "checks": [],
                },
                {
                    "id": "DX-rule",
                    "source_type": "finding",
                    "source_id": "HD-AUTO-005",
                    "title": "Doublon",
                    "priority": "verify",
                    "severity": "medium",
                    "confidence": "high",
                    "confidence_score": 0.9,
                    "checks": [],
                },
            ],
            "registry_analysis": {"available": False},
        }
        out = calibration.calibrate(report)
        ids = {x["id"] for x in out["diagnostic_explanations"]}
        self.assertNotIn("DX-script", ids)
        self.assertIn("DX-rule", ids)
        self.assertEqual(out["diagnostic_engine"]["suppressed_noise_count"], 1)

    def test_duplicate_integration_card_is_removed_when_cluster_exists(self):
        report = {
            "scores": {"global": 86},
            "diagnostic_summary": {"priority_counts": {}},
            "registry_observations": [],
            "diagnostic_engine": {},
            "diagnostic_explanations": [
                {
                    "id": "DX-overkiz-int",
                    "source_type": "registry_integration",
                    "source_id": "overkiz",
                    "title": "Overkiz dégradée",
                    "priority": "verify",
                    "severity": "low",
                    "confidence": "medium",
                    "confidence_score": 0.7,
                    "checks": [],
                },
                {
                    "id": "DX-overkiz-cluster",
                    "source_type": "registry_cluster",
                    "source_id": "overkiz",
                    "title": "3 appareils overkiz indisponibles",
                    "priority": "verify",
                    "severity": "medium",
                    "confidence": "high",
                    "confidence_score": 0.88,
                    "checks": [],
                },
            ],
            "registry_analysis": {"available": True, "integration_health": {"groups": []}, "device_health": {"groups": []}},
        }
        out = calibration.calibrate(report)
        types = [x["source_type"] for x in out["diagnostic_explanations"]]
        self.assertEqual(types, ["registry_cluster"])

    def test_mqtt_cluster_is_replaced_by_individual_device_incident(self):
        report = {
            "scores": {"global": 86},
            "diagnostic_summary": {"priority_counts": {}},
            "registry_observations": [],
            "diagnostic_engine": {},
            "diagnostic_explanations": [
                {
                    "id": "DX-mqtt-cluster",
                    "source_type": "registry_cluster",
                    "source_id": "mqtt",
                    "title": "3 appareils mqtt indisponibles",
                    "priority": "verify",
                    "severity": "medium",
                    "confidence": "high",
                    "confidence_score": 0.88,
                    "checks": [],
                }
            ],
            "registry_analysis": {
                "available": True,
                "integration_health": {
                    "groups": [{"integration": "mqtt", "status": "watch"}]
                },
                "device_health": {
                    "groups": [{
                        "name": "Prise salon",
                        "manufacturer": "Tuya",
                        "model": "plug",
                        "platforms": ["mqtt"],
                        "status": "offline",
                        "core_total": 4,
                        "core_affected": 4,
                        "healthy": 0,
                        "unavailable": 5,
                        "unknown": 0,
                        "missing_state": 0,
                        "affected_ratio": 1.0,
                        "examples": ["switch.prise_salon"],
                    }]
                },
            },
        }
        out = calibration.calibrate(report)
        items = out["diagnostic_explanations"]
        self.assertFalse(any(x.get("source_type") == "registry_cluster" for x in items))
        device = next(x for x in items if x.get("source_type") == "registry_device")
        self.assertEqual(device["source_id"], "Prise salon")
        self.assertIn("availability", " ".join(device["probable_causes"]).lower())


if __name__ == "__main__":
    unittest.main()
