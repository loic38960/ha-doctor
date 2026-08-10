import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import scanner_v082
import resilience_v082
from semantics_v082 import build_flow_confidence_v2, resolve_controller_pair
from resilience_v082 import classify_fallback
from intelligence_v082 import (
    build_contextual_score_preview,
    build_quality_gates_v22,
    sync_final_consistency,
)


class V082Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(scanner_v082.VERSION, "0.8.2")

    def test_flow_quality_warns_when_resolution_is_high_but_certainty_is_low(self):
        report = {
            "flow_confidence": {
                "target_resolution_rate": 1.0,
                "dynamic_target_resolution_rate": 1.0,
                "dynamic_confidence_bands": {"high": 7, "inferred": 41, "heuristic": 4},
                "low_confidence_dynamic_edges": 45,
                "unresolved_dynamic_targets": 0,
            },
            "dependency_graph_meta": {},
        }
        result = build_flow_confidence_v2(report)
        self.assertEqual(result["quality_status"], "warning")
        self.assertAlmostEqual(result["low_confidence_ratio"], 45 / 52, places=3)

    def test_startup_only_writer_is_coordination_not_runtime_conflict(self):
        startup = {
            "effective": {
                "trigger": [{"platform": "homeassistant", "event": "start"}],
                "action": [
                    {
                        "service": "select.select_option",
                        "target": {"entity_id": "select.tarif"},
                        "data": {"option": "hp"},
                    }
                ],
            }
        }
        runtime = {
            "effective": {
                "trigger": [{"platform": "time", "at": "06:00:00"}],
                "action": [
                    {
                        "service": "select.select_option",
                        "target": {"entity_id": "select.tarif"},
                        "data": {"option": "hp"},
                    }
                ],
            }
        }
        result = resolve_controller_pair(startup, runtime, "select.tarif")
        self.assertIsNotNone(result)
        self.assertEqual(result["kind"], "coordinated")
        self.assertEqual(result["reason"], "startup_reconciliation_writer")

    def test_disjoint_fixed_times_are_proven_exclusive(self):
        a = {"effective": {"trigger": [{"platform": "time", "at": "22:00:00"}]}}
        b = {"effective": {"trigger": [{"platform": "time", "at": "06:00:00"}]}}
        result = resolve_controller_pair(a, b, "select.tarif")
        self.assertEqual(result["kind"], "exclusive")
        self.assertEqual(result["reason"], "disjoint_fixed_time_triggers")

    def test_numeric_default_is_not_strong_resilience(self):
        effective = {
            "variables": {
                "power": "{{ states('sensor.ecojoko') | float(0) }}",
            }
        }
        result = classify_fallback(effective, "sensor.ecojoko")
        self.assertEqual(result["level"], "weak")
        self.assertEqual(result["kind"], "numeric_default")

    def test_explicit_invalid_guard_is_strong_resilience(self):
        effective = {
            "condition": [
                {
                    "condition": "template",
                    "value_template": (
                        "{{ states('sensor.ecojoko') not in "
                        "['unknown', 'unavailable'] }}"
                    ),
                }
            ]
        }
        result = classify_fallback(effective, "sensor.ecojoko")
        self.assertEqual(result["level"], "strong")
        self.assertEqual(result["kind"], "explicit_guard")

    def test_resilience_requires_all_consumers_to_be_strong(self):
        original = resilience_v082.effective_automation_map
        report = {
            "architecture_analysis": {
                "critical_dependencies": [
                    {"entity_id": "sensor.ecojoko", "criticality": 93}
                ]
            },
            "dependency_graph": [
                {
                    "automation": "Strong",
                    "references": ["sensor.ecojoko"],
                    "triggers_on": [],
                    "reads": [],
                },
                {
                    "automation": "Weak",
                    "references": ["sensor.ecojoko"],
                    "triggers_on": [],
                    "reads": [],
                },
            ],
        }
        mapping = {
            "Strong": [{
                "effective": {
                    "condition": "{{ states('sensor.ecojoko') not in ['unknown','unavailable'] }}"
                }
            }],
            "Weak": [{
                "effective": {
                    "variables": {"p": "{{ states('sensor.ecojoko') | float(0) }}"}
                }
            }],
        }
        try:
            resilience_v082.effective_automation_map = lambda _report: (mapping, [])
            result = resilience_v082.build_resilience_analysis_v2(report)
        finally:
            resilience_v082.effective_automation_map = original
        self.assertEqual(result["protected_count"], 0)
        self.assertEqual(result["partial_count"], 1)
        self.assertEqual(result["items"][0]["explicit_guard_count"], 1)
        self.assertEqual(result["items"][0]["numeric_default_only_count"], 1)

    def test_contextual_score_preview_does_not_rewrite_primary_score(self):
        report = {
            "scores": {"global": 76},
            "score_meta": {
                "penalty_breakdown": [
                    {"id": "DX-REG-CLUSTER-overkiz", "penalty": 1.28}
                ]
            },
            "operational_context": {
                "diagnostics_deescalated": ["DX-REG-CLUSTER-overkiz"]
            },
            "registry_analysis": {
                "integration_health": {"groups": []},
                "device_health": {
                    "groups": [
                        {
                            "name": "Radiateur A",
                            "platforms": ["overkiz"],
                            "context_factor": 0.55,
                        },
                        {
                            "name": "Radiateur B",
                            "platforms": ["overkiz"],
                            "context_factor": 0.55,
                        },
                    ]
                },
            },
        }
        result = build_contextual_score_preview(report)
        self.assertEqual(report["scores"]["global"], 76)
        self.assertGreater(result["contextual_score_raw"], 76)
        self.assertFalse(result["applied_to_primary_score"])

    def test_final_registry_counter_uses_only_final_plan(self):
        report = {
            "action_plan": {
                "items": [
                    {"id": "a", "priority": "verify", "source_type": "registry_integration", "temporal": {"status": "persistent"}},
                    {"id": "b", "priority": "verify", "source_type": "registry_device", "temporal": {"status": "persistent"}},
                    {"id": "c", "priority": "optimize", "source_type": "finding", "temporal": {"status": "persistent"}},
                ]
            },
            "recommendation_queue": {},
            "diagnostic_summary": {},
            "diagnostic_explanations": [
                {"id": "a", "source_type": "registry_integration", "temporal": {"status": "persistent"}},
                {"id": "b", "source_type": "registry_device", "temporal": {"status": "persistent"}},
                {"id": "suppressed", "source_type": "registry_cluster", "priority": "info", "temporal": {"status": "persistent"}},
            ],
            "registry_observations": [],
            "root_cause_summary": {},
            "temporal_analysis": {},
        }
        sync_final_consistency(report)
        root = report["root_cause_summary"]
        self.assertEqual(root["actionable_registry_incidents"], 2)
        self.assertEqual(root["detected_registry_incidents"], 3)
        self.assertEqual(root["cluster_incidents"], 0)

    def test_quality_gates_warn_for_unproven_semantics_and_partial_resilience(self):
        report = {
            "quality_gates": {"gates": []},
            "scan_consistency": {"inventory_matches_entity_health": True},
            "action_plan": {"counts": {"action_now": 0}, "items": []},
            "diagnostic_summary": {"priority_counts": {"action_now": 0}},
            "root_cause_summary": {"actionable_registry_incidents": 0},
            "flow_confidence": {
                "quality_status": "warning",
                "low_confidence_ratio": 0.86,
                "unresolved_dynamic_targets": 0,
            },
            "condition_semantics": {
                "resolved_pair_count": 5,
                "unproven_pair_count": 2,
                "parse_errors": [],
            },
            "resilience_analysis": {
                "protected_count": 2,
                "partial_count": 1,
                "review_count": 0,
            },
        }
        gates = build_quality_gates_v22(report)
        self.assertEqual(gates["overall"], "warning")
        by_key = {item["key"]: item for item in gates["gates"]}
        self.assertEqual(by_key["flow_confidence"]["status"], "warning")
        self.assertEqual(by_key["condition_semantics"]["status"], "warning")
        self.assertEqual(by_key["resilience"]["status"], "warning")


if __name__ == "__main__":
    unittest.main()
