import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from flow_v080 import analyze_effective_automation, resolve_variable_lineage
from intelligence_v080 import (
    build_architecture_v2,
    build_automation_coverage,
    build_maintenance_debt_v2,
    build_quality_gates_v2,
)
import scanner_v080


class V080Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(scanner_v080.VERSION, "0.8.0")

    def test_variable_lineage_resolves_chained_dynamic_targets(self):
        automation = {
            "variables": {
                "clims": [
                    {"entity": "climate.salon"},
                    {"entity": "climate.chambre"},
                ],
                "next_item": "{{ clims | first }}",
                "next_clim": "{{ next_item.entity }}",
            }
        }
        lineage = resolve_variable_lineage(automation)
        self.assertEqual(
            lineage["next_clim"],
            {"climate.salon", "climate.chambre"},
        )

    def test_flow_resolves_switch_climates_and_script_call(self):
        automation = {
            "variables": {
                "pompe_entity": "switch.pompe_piscine",
                "clims": [
                    {"entity": "climate.salon"},
                    {"entity": "climate.chambre_parentale"},
                ],
                "next_item": "{{ clims | first }}",
                "next_clim": "{{ next_item.entity }}",
                "notify_script_entity": "script.notifier_mogo_loic",
            },
            "action": [
                {
                    "service": "switch.turn_on",
                    "target": {"entity_id": "{{ pompe_entity }}"},
                },
                {
                    "service": "climate.set_hvac_mode",
                    "target": {"entity_id": "{{ next_clim }}"},
                    "data": {"hvac_mode": "cool"},
                },
                {
                    "service": "script.turn_on",
                    "target": {"entity_id": "{{ notify_script_entity }}"},
                },
            ],
        }
        flow = analyze_effective_automation(automation, alias="PV")
        controls = {item["entity_id"]: item["confidence"] for item in flow["controls"]}
        calls = {item["entity_id"] for item in flow["calls"]}

        self.assertIn("switch.pompe_piscine", controls)
        self.assertIn("climate.salon", controls)
        self.assertIn("climate.chambre_parentale", controls)
        self.assertIn("script.notifier_mogo_loic", calls)
        self.assertEqual(flow["target_attempts"], 3)
        self.assertEqual(flow["resolved_target_attempts"], 3)
        self.assertEqual(flow["dynamic_target_attempts"], 3)
        self.assertEqual(flow["dynamic_target_resolved"], 3)
        self.assertEqual(flow["unresolved_dynamic_targets"], [])

    def test_unresolved_dynamic_target_does_not_persist_template_text(self):
        automation = {
            "action": [
                {
                    "service": "switch.turn_on",
                    "target": {"entity_id": "{{ unknown_runtime_value }}"},
                }
            ]
        }
        flow = analyze_effective_automation(automation)
        self.assertEqual(len(flow["unresolved_dynamic_targets"]), 1)
        text = str(flow["unresolved_dynamic_targets"][0])
        self.assertNotIn("{{", text)
        self.assertNotIn("unknown_runtime_value }}", text)
        self.assertIn("unknown_runtime_value", text)

    def test_read_fanout_no_longer_beats_physical_controls(self):
        many_reads = [f"sensor.read_{idx}" for idx in range(55)]
        report = {
            "inventory": {"states": 500},
            "registry_analysis": {"integration_health": {"total": 10}},
            "dependency_graph_meta": {
                "entity_edges": 70,
                "control_edges": 4,
                "call_edges": 0,
                "unresolved_dynamic_target_count": 0,
                "target_resolution_rate": 1.0,
                "dynamic_target_resolution_rate": 1.0,
            },
            "dependency_graph": [
                {
                    "automation": "Reader",
                    "source": "reader.yaml",
                    "triggers_on": [],
                    "controls": [],
                    "calls": [],
                    "reads": many_reads,
                    "references": many_reads,
                    "dynamic_controls": [],
                    "unresolved_dynamic_targets": [],
                },
                {
                    "automation": "Fire safety",
                    "source": "security.yaml",
                    "triggers_on": ["binary_sensor.smoke"],
                    "controls": [
                        "cover.one",
                        "cover.two",
                        "cover.three",
                        "cover.four",
                    ],
                    "calls": [],
                    "reads": [],
                    "references": [
                        "binary_sensor.smoke",
                        "cover.one",
                        "cover.two",
                        "cover.three",
                        "cover.four",
                    ],
                    "dynamic_controls": [],
                    "unresolved_dynamic_targets": [],
                },
            ],
        }
        architecture = build_architecture_v2(report)
        risks = {
            item["automation"]: item["risk_index"]
            for item in architecture["automation_risk_profiles"]
        }
        self.assertGreater(risks["Fire safety"], risks["Reader"])
        self.assertLess(risks["Reader"], 6.0)

    def test_coverage_uses_healthy_runtime_automations(self):
        report = {
            "inventory": {
                "automations_detected": 52,
                "domains": {"automation": 61},
            },
            "registry_analysis": {
                "integration_health": {
                    "groups": [
                        {
                            "integration": "automation",
                            "total": 61,
                            "healthy": 52,
                            "unavailable": 9,
                            "unknown": 0,
                        }
                    ]
                },
                "orphan_analysis": {
                    "local_unavailable_candidates": [
                        {
                            "entity_id": f"automation.old_{idx}",
                            "platform": "automation",
                        }
                        for idx in range(9)
                    ]
                },
            },
            "findings": [
                {
                    "rule_id": "HD-CFG-005",
                    "title": "old",
                    "summary": "old",
                    "recommendation": "old",
                }
            ],
            "diagnostic_explanations": [],
        }
        coverage = build_automation_coverage(report)
        self.assertEqual(coverage["coverage_ratio"], 1.0)
        self.assertEqual(coverage["coverage_gap"], 0)
        self.assertEqual(coverage["runtime_unavailable_automations"], 9)
        self.assertEqual(coverage["stale_registry_automation_candidates"], 9)
        self.assertFalse(coverage["unavailable_registry_entries_count_as_coverage_gap"])
        self.assertIn("100.0", report["findings"][0]["summary"])

    def test_maintenance_debt_v2_does_not_double_count_unavailable_coverage(self):
        report = {
            "findings": [
                {"rule_id": "HD-CFG-001", "examples": [{} for _ in range(7)]},
                {"rule_id": "HD-SEC-003", "examples": [{} for _ in range(8)]},
                {"rule_id": "HD-SEC-001", "examples": [{} for _ in range(3)]},
                {"rule_id": "HD-AUTO-009", "examples": [{}]},
                {"rule_id": "HD-AUTO-005", "examples": [{}]},
                {"rule_id": "HD-AUTO-001", "examples": [{}, {}]},
                {"rule_id": "HD-AUTO-002", "examples": [{}]},
            ],
            "registry_analysis": {
                "orphan_analysis": {
                    "probable_orphan_count": 0,
                    "review_candidate_count": 29,
                }
            },
            "automation_coverage": {
                "coverage_ratio": 1.0,
                "coverage_gap": 0,
                "stale_registry_automation_candidates": 9,
            },
        }
        debt = build_maintenance_debt_v2(report)
        self.assertEqual(debt["automation_coverage_gap"], 0)
        self.assertFalse(debt["unavailable_automations_double_counted"])
        self.assertTrue(debt["double_count_protection"])
        self.assertLess(debt["score"], 65)

    def test_quality_gate_checks_flow_and_coverage(self):
        report = {
            "quality_gates": {
                "gates": [
                    {"key": "api", "label": "API", "status": "pass", "detail": "ok"},
                    {"key": "yaml", "label": "YAML", "status": "pass", "detail": "ok"},
                    {"key": "privacy", "label": "Privacy", "status": "pass", "detail": "ok"},
                ]
            },
            "dependency_graph_meta": {
                "target_resolution_rate": 0.95,
                "dynamic_target_resolution_rate": 0.90,
                "semantic_match_rate": 1.0,
                "unresolved_dynamic_target_count": 2,
                "flow_reparse_errors": [],
            },
            "automation_coverage": {
                "coverage_ratio": 1.0,
                "coverage_gap": 0,
                "yaml_automations_analyzed": 52,
                "expected_analyzable_automations": 52,
            },
            "temporal_analysis": {"enabled": True, "scan_count": 4},
        }
        quality = build_quality_gates_v2(report)
        flow = next(item for item in quality["gates"] if item["key"] == "flow")
        coverage = next(
            item for item in quality["gates"]
            if item["key"] == "automation_coverage"
        )
        self.assertEqual(flow["status"], "pass")
        self.assertEqual(coverage["status"], "pass")
        self.assertEqual(quality["overall"], "pass")


if __name__ == "__main__":
    unittest.main()
