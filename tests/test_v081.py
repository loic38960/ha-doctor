import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import scanner as core_scanner
import scanner_v081
import intelligence_v081
from semantics_v081 import build_flow_confidence, required_state_guards
from callgraph_v081 import build_transitive_call_graph


class V081Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(scanner_v081.VERSION, "0.8.1")

    def test_scanner_collapses_multiple_state_reads_to_one_network_read(self):
        original_safe = core_scanner._safe_api_get
        original_base_scan = scanner_v081.base.scan
        original_v080 = scanner_v081.intelligence_v080.enrich_v080
        original_v081 = scanner_v081.intelligence_v081.enrich_v081
        network_calls = []

        def fake_safe(path, errors):
            if path == "/core/api/states":
                network_calls.append(path)
                return [{"entity_id": "sensor.test", "state": "1"}]
            return {}

        def fake_base_scan(include_yaml=True):
            first = core_scanner._safe_api_get("/core/api/states", [])
            second = core_scanner._safe_api_get("/core/api/states", [])
            third = core_scanner._safe_api_get("/core/api/states", [])
            self.assertEqual(first, second)
            self.assertEqual(second, third)
            return {"privacy": {}, "scan_consistency": {}}

        try:
            core_scanner._safe_api_get = fake_safe
            scanner_v081.base.scan = fake_base_scan
            scanner_v081.intelligence_v080.enrich_v080 = lambda report: report
            scanner_v081.intelligence_v081.enrich_v081 = (
                lambda report, states_snapshot=None: report
            )
            report = scanner_v081.scan()
        finally:
            core_scanner._safe_api_get = original_safe
            scanner_v081.base.scan = original_base_scan
            scanner_v081.intelligence_v080.enrich_v080 = original_v080
            scanner_v081.intelligence_v081.enrich_v081 = original_v081

        self.assertEqual(len(network_calls), 1)
        self.assertEqual(report["scan_consistency"]["state_api_requests_collapsed"], 3)
        self.assertEqual(report["scan_consistency"]["state_api_network_reads"], 1)

    def test_snapshot_counts_are_identical_between_inventory_and_entity_health(self):
        states = [
            {"entity_id": "sensor.ok", "state": "1"},
            {"entity_id": "sensor.offline", "state": "unavailable"},
            {"entity_id": "sensor.unknown", "state": "unknown"},
            {"entity_id": "button.stateless", "state": "unknown"},
        ]
        report = {"inventory": {}, "privacy": {}, "findings": []}
        consistency = intelligence_v081.synchronize_state_snapshot(report, states)
        self.assertTrue(consistency["inventory_matches_entity_health"])
        self.assertEqual(report["inventory"]["unavailable_count"], 1)
        self.assertEqual(report["entity_health"]["unavailable"]["total"], 1)
        self.assertEqual(report["inventory"]["unknown_count"], 2)
        self.assertEqual(report["entity_health"]["unknown"]["total"], 2)

    def test_flow_confidence_separates_resolved_from_certainty(self):
        report = {
            "dependency_graph_meta": {
                "control_edges": 5,
                "target_resolution_rate": 1.0,
                "dynamic_target_resolution_rate": 1.0,
                "unresolved_dynamic_target_count": 0,
            },
            "dependency_graph": [
                {
                    "dynamic_controls": [
                        {"entity_id": "climate.a", "confidence": 0.9},
                        {"entity_id": "climate.b", "confidence": 0.72},
                        {"entity_id": "climate.c", "confidence": 0.55},
                    ]
                }
            ],
        }
        result = build_flow_confidence(report)
        self.assertEqual(result["dynamic_confidence_bands"]["high"], 1)
        self.assertEqual(result["dynamic_confidence_bands"]["inferred"], 1)
        self.assertEqual(result["dynamic_confidence_bands"]["heuristic"], 1)
        self.assertEqual(result["static_control_edges"], 2)
        self.assertEqual(result["low_confidence_dynamic_edges"], 2)

    def test_condition_guards_keep_and_but_ignore_or(self):
        guards = required_state_guards([
            {
                "condition": "state",
                "entity_id": "input_select.mode",
                "state": "ete",
            },
            "{{ is_state('input_boolean.enabled', 'on') }}",
        ])
        self.assertEqual(guards["input_select.mode"], {"ete"})
        self.assertEqual(guards["input_boolean.enabled"], {"on"})

        ambiguous = required_state_guards({
            "condition": "or",
            "conditions": [
                {
                    "condition": "state",
                    "entity_id": "input_select.mode",
                    "state": "ete",
                },
                {
                    "condition": "state",
                    "entity_id": "input_select.mode",
                    "state": "hiver",
                },
            ],
        })
        self.assertEqual(ambiguous, {})

    def test_transitive_script_graph_reaches_downstream_control(self):
        original_root = core_scanner.CONFIG_ROOT
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts.yaml").write_text(
                "notify_parent:\n"
                "  sequence:\n"
                "    - service: script.notify_child\n"
                "notify_child:\n"
                "  sequence:\n"
                "    - service: light.turn_on\n"
                "      target:\n"
                "        entity_id: light.salon\n",
                encoding="utf-8",
            )
            core_scanner.CONFIG_ROOT = root
            report = {
                "privacy": {},
                "dependency_graph": [
                    {
                        "automation": "Caller",
                        "source": "automations.yaml",
                        "calls": ["script.notify_parent"],
                    }
                ],
                "architecture_analysis": {},
            }
            try:
                result = build_transitive_call_graph(report)
            finally:
                core_scanner.CONFIG_ROOT = original_root

        node = report["dependency_graph"][0]
        self.assertIn("light.salon", node["transitive_controls"])
        self.assertTrue(any(
            item["entity_id"] == "script.notify_child"
            for item in node["transitive_calls"]
        ))
        self.assertEqual(result["recursion_cycle_count"], 0)

    def test_solar_offline_is_deescalated_when_sun_is_below_horizon(self):
        report = {
            "generated_at": "2026-08-10T04:57:51Z",
            "home_assistant": {"time_zone": "Europe/Paris"},
            "registry_analysis": {
                "integration_health": {
                    "groups": [
                        {
                            "integration": "huawei_solar",
                            "status": "offline",
                            "missing_state": 0,
                        }
                    ]
                },
                "device_health": {"groups": []},
            },
            "diagnostic_explanations": [
                {
                    "id": "DX-REG-INT-huawei_solar",
                    "source_type": "registry_integration",
                    "source_id": "huawei_solar",
                    "priority": "verify",
                    "priority_label": "À vérifier",
                }
            ],
            "action_plan": {
                "items": [{"id": "DX-REG-INT-huawei_solar"}],
                "top": [{"id": "DX-REG-INT-huawei_solar"}],
            },
            "recommendation_queue": {
                "items": [{"id": "DX-REG-INT-huawei_solar"}]
            },
            "registry_observations": [],
        }
        states = [{"entity_id": "sun.sun", "state": "below_horizon"}]
        context = intelligence_v081.calibrate_operational_context(report, states)
        group = report["registry_analysis"]["integration_health"]["groups"][0]
        self.assertEqual(group["status"], "watch")
        self.assertIn("huawei_solar", context["solar_integrations_deescalated"])
        self.assertEqual(report["action_plan"]["items"], [])
        self.assertEqual(report["diagnostic_explanations"][0]["priority"], "info")


if __name__ == "__main__":
    unittest.main()
