import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
sys.path.insert(0, str(APP))

import diagnostic_explain
import scanner_v050


class ExplainFindingTests(unittest.TestCase):
    def test_duplicate_numeric_writers_get_high_confidence_playbook(self):
        item = {
            "rule_id": "HD-AUTO-009",
            "title": "Deux automatisations écrivent les mêmes compteurs numériques",
            "severity": "high",
            "domain": "automations",
            "priority": "action_now",
            "priority_label": "À corriger maintenant",
            "summary": "1 paire détectée",
            "examples": [{
                "automations": ["VB ancienne", "VB nouvelle"],
                "shared_numeric_targets": ["input_number.vb_energy_kwh"],
            }],
        }
        result = diagnostic_explain.explain_finding(item)
        self.assertEqual(result["confidence"], "high")
        self.assertGreaterEqual(result["confidence_score"], 0.9)
        self.assertEqual(result["priority"], "action_now")
        self.assertGreaterEqual(len(result["checks"]), 3)
        self.assertFalse(result["automatic_fix"])
        self.assertTrue(result["read_only"])

    def test_security_explanation_does_not_copy_secret_value(self):
        item = {
            "rule_id": "HD-SEC-001",
            "title": "Secret potentiel",
            "severity": "high",
            "domain": "security",
            "priority": "action_now",
            "summary": "1 clé sensible potentielle",
            "examples": [{"file": "zigbee2mqtt/configuration.yaml", "line": 6, "key": "password", "value": "DO_NOT_COPY"}],
        }
        result = diagnostic_explain.explain_finding(item)
        rendered = repr(result)
        self.assertNotIn("DO_NOT_COPY", rendered)
        self.assertIn("zigbee2mqtt/configuration.yaml", rendered)
        self.assertIn("password", rendered)


class RegistryExplanationTests(unittest.TestCase):
    def _registry(self):
        return {
            "available": True,
            "integration_health": {
                "groups": [
                    {
                        "integration": "smartthings",
                        "status": "offline",
                        "core_total": 15,
                        "core_affected": 15,
                        "healthy": 0,
                        "unavailable": 19,
                        "unknown": 0,
                        "missing_state": 0,
                        "affected_ratio": 1.0,
                        "examples": ["sensor.washer_power"],
                    },
                    {
                        "integration": "tesla_fleet",
                        "status": "watch",
                        "status_note": "Valeurs Tesla potentiellement indisponibles pendant la veille du véhicule.",
                        "transient_or_sleep_tolerant": True,
                        "core_total": 30,
                        "core_affected": 26,
                        "healthy": 4,
                        "unavailable": 2,
                        "unknown": 47,
                        "missing_state": 0,
                        "affected_ratio": 0.867,
                    },
                    {
                        "integration": "mqtt",
                        "status": "watch",
                        "core_total": 349,
                        "core_affected": 10,
                        "healthy": 300,
                        "unavailable": 10,
                        "unknown": 0,
                        "missing_state": 0,
                        "affected_ratio": 0.03,
                    },
                ]
            },
            "device_health": {
                "groups": [
                    {
                        "name": "Lave-linge",
                        "manufacturer": "Samsung",
                        "model": "WM",
                        "platforms": ["smartthings"],
                        "status": "offline",
                        "core_total": 12,
                        "core_affected": 12,
                        "healthy": 0,
                        "unavailable": 16,
                        "unknown": 0,
                        "missing_state": 0,
                        "affected_ratio": 1.0,
                        "examples": ["sensor.lave_linge_power"],
                    },
                    {
                        "name": "Prise bureau",
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
                        "examples": ["switch.prise_bureau"],
                    },
                ]
            },
        }

    def test_offline_integration_is_one_root_cause(self):
        incidents, observations = diagnostic_explain.explain_registry(self._registry())
        smartthings = [x for x in incidents if x.get("source_id") == "smartthings"]
        self.assertEqual(len(smartthings), 1)
        self.assertEqual(smartthings[0]["source_type"], "registry_integration")
        self.assertEqual(smartthings[0]["confidence"], "high")
        # The washer must not create a duplicate device incident because the parent integration is offline.
        self.assertFalse(any(x.get("source_id") == "Lave-linge" for x in incidents))
        self.assertTrue(any(x.get("integration") == "tesla_fleet" for x in observations))

    def test_mqtt_device_offline_is_localized_incident(self):
        incidents, _ = diagnostic_explain.explain_registry(self._registry())
        device = next(x for x in incidents if x.get("source_id") == "Prise bureau")
        self.assertEqual(device["source_type"], "registry_device")
        self.assertIn("availability", " ".join(device["probable_causes"]).lower())


class ActionPlanTests(unittest.TestCase):
    def test_action_plan_prioritizes_action_now_before_registry_verify(self):
        explanations = [
            {
                "id": "verify",
                "title": "Intégration hors ligne",
                "priority": "verify",
                "severity": "medium",
                "confidence": "high",
                "confidence_score": 0.95,
                "checks": [{"step": 1, "title": "Vérifier", "detail": "x"}],
            },
            {
                "id": "fix",
                "title": "Erreur de configuration",
                "priority": "action_now",
                "severity": "medium",
                "confidence": "high",
                "confidence_score": 0.9,
                "checks": [{"step": 1, "title": "Corriger", "detail": "x"}],
            },
        ]
        plan = diagnostic_explain.build_action_plan(explanations)
        self.assertEqual(plan["items"][0]["id"], "fix")
        self.assertEqual(plan["counts"]["action_now"], 1)
        self.assertEqual(plan["counts"]["verify"], 1)


class V050ScannerTests(unittest.TestCase):
    def test_scan_adds_explanations_without_changing_score(self):
        base_report = {
            "product": "HA Doctor",
            "version": "0.4.1",
            "scores": {"global": 86, "domains": {"automations": 72}},
            "score_meta": {"model": "priority_v2.1-preview", "registry_scoring": False},
            "diagnostic_summary": {
                "priority_counts": {"action_now": 1, "verify": 0, "optimize": 0, "info": 0}
            },
            "findings": [{
                "rule_id": "HD-AUTO-005",
                "title": "Actions consécutives identiques",
                "severity": "medium",
                "domain": "automations",
                "priority": "action_now",
                "priority_label": "À corriger maintenant",
                "summary": "1 doublon",
                "examples": [{"alias": "Test", "source": "automations.yaml"}],
            }],
            "registry_analysis": {
                "available": True,
                "integration_health": {"problematic": 0, "groups": []},
                "device_health": {"problematic": 0, "groups": []},
            },
            "privacy": {},
        }
        with patch.object(scanner_v050.v041, "scan", return_value=base_report):
            report = scanner_v050.scan()

        self.assertEqual(report["version"], "0.5.0")
        self.assertEqual(report["scores"]["global"], 86)
        self.assertEqual(report["score_meta"]["model"], "priority_v3-explain-preview")
        self.assertFalse(report["score_meta"]["explanatory_scoring"])
        self.assertEqual(report["diagnostic_engine"]["mode"], "deterministic_local")
        self.assertFalse(report["diagnostic_engine"]["external_ai_used"])
        self.assertEqual(len(report["diagnostic_explanations"]), 1)
        self.assertEqual(report["action_plan"]["items"][0]["source_id"], "HD-AUTO-005")
        self.assertFalse(report["privacy"]["explanatory_engine_external_ai_used"])


if __name__ == "__main__":
    unittest.main()
