import copy
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from intelligence_v070 import clean_dependency_graph, enrich_v070
from share_export import build_anonymized_report
import app
import scanner_v070


class V070Tests(unittest.TestCase):
    def base_report(self):
        return {
            "product": "HA Doctor",
            "generated_at": "2026-08-08T22:00:00Z",
            "scores": {"global": 86, "domains": {}},
            "privacy": {
                "secrets_yaml_read": False,
                "raw_states_persisted": False,
            },
            "inventory": {
                "states": 500,
                "unavailable_count": 50,
                "unknown_count": 20,
                "automations_detected": 3,
                "domains": {
                    "automation": 3,
                    "sensor": 200,
                    "switch": 20,
                    "input_boolean": 10,
                    "todo": 1,
                    "script": 4,
                },
            },
            "dependency_graph": [
                {
                    "automation": "Pool control",
                    "source": "packages/pool.yaml",
                    "references": [
                        "sensor.grid_power", "switch.pool_pump", "switch.turn_on",
                        "input_boolean.pool_lock", "input_boolean.turn_on",
                    ],
                    "triggers_on": ["sensor.grid_power"],
                    "controls": ["switch.pool_pump", "input_boolean.pool_lock"],
                },
                {
                    "automation": "Pool safety",
                    "source": "packages/pool.yaml",
                    "references": ["switch.pool_pump", "switch.turn_off"],
                    "triggers_on": ["switch.pool_pump"],
                    "controls": ["switch.pool_pump"],
                },
                {
                    "automation": "Shopping",
                    "source": "automations.yaml",
                    "references": ["todo.get_items", "todo.shopping"],
                    "triggers_on": [],
                    "controls": [],
                },
            ],
            "registry_analysis": {
                "available": True,
                "integration_health": {
                    "total": 4,
                    "groups": [
                        {
                            "integration": "demo_cloud",
                            "examples": ["sensor.grid_power"],
                            "status": "offline",
                        }
                    ],
                },
                "device_health": {"total": 3, "groups": []},
                "orphan_analysis": {
                    "probable_orphan_count": 0,
                    "review_candidate_count": 5,
                },
            },
            "registry_observations": [],
            "diagnostics": {
                "api_errors": [],
                "yaml_parse_errors": [],
                "unresolved_blueprints": [],
            },
            "findings": [
                {
                    "rule_id": "HD-CFG-001",
                    "examples": [{"entity_id": "sensor.old_one"}, {"entity_id": "sensor.old_two"}],
                },
                {
                    "rule_id": "HD-SEC-003",
                    "examples": [{"file": "archive.yaml"}],
                },
            ],
            "diagnostic_summary": {
                "priority_counts": {"action_now": 99, "verify": 99, "optimize": 99}
            },
            "diagnostic_explanations": [
                {
                    "id": "DX-HD-SEC-001",
                    "source_type": "finding",
                    "source_id": "HD-SEC-001",
                    "rule_id": "HD-SEC-001",
                    "title": "Sensitive value",
                    "priority": "action_now",
                    "priority_label": "À corriger maintenant",
                    "severity": "high",
                    "domain": "security",
                    "confidence": "high",
                    "confidence_label": "Élevée",
                    "confidence_score": 0.95,
                    "diagnosis": "Secret candidate",
                    "impact": "Exposure risk",
                    "checks": [],
                    "evidence": [],
                },
                {
                    "id": "DX-HD-AUTO-003",
                    "source_type": "finding",
                    "source_id": "HD-AUTO-003",
                    "rule_id": "HD-AUTO-003",
                    "title": "Shared control",
                    "priority": "verify",
                    "priority_label": "À vérifier",
                    "severity": "medium",
                    "domain": "automations",
                    "confidence": "medium",
                    "confidence_label": "Moyenne",
                    "confidence_score": 0.72,
                    "diagnosis": "Shared entities",
                    "impact": "Possible conflict",
                    "checks": [],
                    "evidence": [
                        {"text": "switch.pool_pump"},
                        {"text": "input_boolean.pool_lock"},
                    ],
                },
                {
                    "id": "DX-REG-INT-demo_cloud",
                    "source_type": "registry_integration",
                    "source_id": "demo_cloud",
                    "title": "demo_cloud offline",
                    "priority": "verify",
                    "priority_label": "À vérifier",
                    "severity": "medium",
                    "domain": "entities",
                    "confidence": "high",
                    "confidence_label": "Élevée",
                    "confidence_score": 0.92,
                    "diagnosis": "Integration offline",
                    "impact": "States unavailable",
                    "checks": [],
                    "evidence": [],
                },
                {
                    "id": "DX-HD-ENT-001",
                    "source_type": "finding",
                    "source_id": "HD-ENT-001",
                    "rule_id": "HD-ENT-001",
                    "title": "Unavailable entities",
                    "priority": "verify",
                    "priority_label": "À vérifier",
                    "severity": "medium",
                    "domain": "entities",
                    "confidence": "medium",
                    "confidence_label": "Moyenne",
                    "confidence_score": 0.68,
                    "diagnosis": "Raw unavailable volume",
                    "impact": "Generic",
                    "checks": [],
                    "evidence": [],
                },
            ],
        }

    def test_version_imports_match(self):
        self.assertEqual(app.VERSION, "0.7.0")
        self.assertEqual(scanner_v070.VERSION, "0.7.0")

    def test_service_calls_are_removed_from_dependency_references(self):
        report = self.base_report()
        clean_dependency_graph(report)
        refs = {x for node in report["dependency_graph"] for x in node["references"]}
        self.assertNotIn("switch.turn_on", refs)
        self.assertNotIn("switch.turn_off", refs)
        self.assertNotIn("input_boolean.turn_on", refs)
        self.assertNotIn("todo.get_items", refs)
        self.assertIn("todo.shopping", refs)
        self.assertGreaterEqual(report["dependency_graph_meta"]["service_references_removed"], 4)

    def test_helper_fanout_is_discounted(self):
        with tempfile.TemporaryDirectory() as d:
            report = enrich_v070(self.base_report(), str(Path(d) / "history.json"))
            item = next(x for x in report["diagnostic_explanations"] if x["id"] == "DX-HD-AUTO-003")
            dep = item["dependency_impact"]
            self.assertTrue(dep["helper_fanout_discounted"])
            kinds = {x["entity_id"]: x["kind"] for x in dep["top_entities"]}
            self.assertEqual(kinds["switch.pool_pump"], "actuator")
            self.assertEqual(kinds["input_boolean.pool_lock"], "helper")
            pump = next(x for x in dep["top_entities"] if x["entity_id"] == "switch.pool_pump")
            helper = next(x for x in dep["top_entities"] if x["entity_id"] == "input_boolean.pool_lock")
            self.assertGreater(pump["weight"], helper["weight"])

    def test_final_summary_is_synchronized_with_action_plan(self):
        with tempfile.TemporaryDirectory() as d:
            report = enrich_v070(self.base_report(), str(Path(d) / "history.json"))
            self.assertEqual(report["diagnostic_summary"]["priority_counts"]["action_now"], report["action_plan"]["counts"]["action_now"])
            self.assertEqual(report["diagnostic_summary"]["priority_counts"]["verify"], report["action_plan"]["counts"]["verify"])
            self.assertEqual(report["diagnostic_summary"]["priority_counts"]["optimize"], report["action_plan"]["counts"]["optimize"])
            consistency = next(x for x in report["quality_gates"]["gates"] if x["key"] == "consistency")
            self.assertEqual(consistency["status"], "pass")

    def test_root_cause_suppresses_generic_entity_volume(self):
        with tempfile.TemporaryDirectory() as d:
            report = enrich_v070(self.base_report(), str(Path(d) / "history.json"))
            ids = [x["id"] for x in report["action_plan"]["items"]]
            self.assertIn("DX-REG-INT-demo_cloud", ids)
            self.assertNotIn("DX-HD-ENT-001", ids)

    def test_raw_unavailable_volume_does_not_change_v4_score(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = self.base_report()
            b = copy.deepcopy(a)
            b["inventory"]["unavailable_count"] = 9999
            b["inventory"]["unknown_count"] = 9999
            first = enrich_v070(a, str(Path(d1) / "history.json"))
            second = enrich_v070(b, str(Path(d2) / "history.json"))
            self.assertEqual(first["scores"]["global"], second["scores"]["global"])
            self.assertFalse(first["score_meta"]["raw_entity_volume_scoring"])

    def test_temporal_migration_accepts_v3_history_and_sets_first_seen(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history.json"
            path.write_text('[{"generated_at":"2026-08-08T20:00:00Z","health_score_v3":79,"active_ids":["DX-HD-SEC-001"]}]', encoding="utf-8")
            report = enrich_v070(self.base_report(), str(path))
            self.assertEqual(report["temporal_analysis"]["previous_score"], 79)
            persistent = next(x for x in report["diagnostic_explanations"] if x["id"] == "DX-HD-SEC-001")
            self.assertEqual(persistent["temporal"]["status"], "persistent")
            new = next(x for x in report["diagnostic_explanations"] if x["id"] == "DX-HD-AUTO-003")
            self.assertIsNotNone(new["temporal"]["first_seen"])

    def test_architecture_exposes_shared_actuator_and_clean_graph(self):
        with tempfile.TemporaryDirectory() as d:
            report = enrich_v070(self.base_report(), str(Path(d) / "history.json"))
            architecture = report["architecture_analysis"]
            self.assertGreaterEqual(architecture["shared_actuator_count"], 1)
            shared_ids = [x["entity_id"] for x in architecture["shared_actuators"]]
            self.assertIn("switch.pool_pump", shared_ids)
            self.assertEqual(report["dependency_graph_meta"]["service_calls_are_entities"], False)

    def test_anonymized_export_keeps_aggregates_without_identifiers(self):
        with tempfile.TemporaryDirectory() as d:
            report = enrich_v070(self.base_report(), str(Path(d) / "history.json"))
            export = build_anonymized_report(report)
            text = str(export)
            self.assertNotIn("switch.pool_pump", text)
            self.assertNotIn("demo_cloud", text)
            self.assertIn("architecture_summary", export)
            self.assertFalse(export["privacy"]["entity_ids_included"])
            self.assertTrue(export["export_meta"]["identifiers_removed"])

    def test_report_schema_and_privacy_guards_are_present(self):
        with tempfile.TemporaryDirectory() as d:
            report = enrich_v070(self.base_report(), str(Path(d) / "history.json"))
            self.assertEqual(report["report_schema"]["version"], "ha-doctor-report/0.7")
            self.assertFalse(report["privacy"]["architecture_raw_state_values_persisted"])
            self.assertFalse(report["privacy"]["automatic_configuration_changes"])
            self.assertTrue(report["diagnostic_engine"]["read_only"])


if __name__ == "__main__":
    unittest.main()
