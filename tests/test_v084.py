import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import lineage_v084
import scanner
import semantics_v084
from consistency_v084 import validate_report_consistency_v4
from resilience_v084 import build_resilience_recommendations_v1
from temporal_v084 import apply_temporal_v31


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class V084Tests(unittest.TestCase):
    def test_version_modules(self):
        import scanner_v084
        import intelligence_v084
        import app_v084
        self.assertEqual(scanner_v084.VERSION, "0.8.4")
        self.assertEqual(intelligence_v084.VERSION, "0.8.4")
        self.assertEqual(app_v084.VERSION, "0.8.4")

    def test_flow_metadata_is_synchronized_after_promotion(self):
        report = {
            "flow_confidence": {
                "model": "flow_confidence_v3",
                "dynamic_confidence_bands": {"high": 52, "inferred": 0, "heuristic": 0},
                "literal_confirmed_promotions": 45,
                "review_required_dynamic_edges": 0,
                "review_required_ratio": 0.0,
                "low_confidence_dynamic_edges": 0,
                "low_confidence_ratio": 0.0,
            },
            "dependency_graph_meta": {
                "low_confidence_dynamic_edges": 45,
                "review_required_dynamic_edges": 45,
                "confidence_model": "flow_confidence_v2",
            },
        }
        result = semantics_v084.normalize_flow_metadata_v31(report)
        meta = report["dependency_graph_meta"]
        self.assertEqual(result["model"], "flow_confidence_v3.1")
        self.assertEqual(meta["low_confidence_dynamic_edges"], 0)
        self.assertEqual(meta["review_required_dynamic_edges"], 0)
        self.assertEqual(meta["confidence_model"], result["model"])

    def test_architecture_is_recomputed_from_promoted_confidence(self):
        report = {
            "inventory": {"states": 10},
            "registry_analysis": {"integration_health": {"total": 1}},
            "dependency_graph_meta": {
                "entity_edges": 1,
                "control_edges": 1,
                "call_edges": 0,
                "target_resolution_rate": 1.0,
                "dynamic_target_resolution_rate": 1.0,
                "unresolved_dynamic_target_count": 0,
            },
            "flow_confidence": {"model": "flow_confidence_v3.1"},
            "dependency_graph": [{
                "automation": "Dynamic climate",
                "source": "packages/test.yaml",
                "triggers_on": [],
                "controls": ["climate.salon"],
                "reads": [],
                "calls": [],
                "references": ["climate.salon"],
                "dynamic_controls": [{"entity_id": "climate.salon", "confidence": 0.90}],
                "unresolved_dynamic_targets": [],
            }],
        }
        result = semantics_v084.recompute_architecture_post_flow(report)
        hotspot = next(x for x in result["top_hotspots"] if x["entity_id"] == "climate.salon")
        self.assertTrue(result["post_flow_recomputed"])
        self.assertEqual(result["model"], "architecture_v3_post_flow")
        self.assertAlmostEqual(hotspot["average_control_confidence"], 0.90, places=2)

    def test_controller_phase_handoff_is_not_left_as_contradiction(self):
        original = semantics_v084.sem_v1.effective_automation_map
        report = {
            "condition_semantics": {
                "resolved_pair_count": 0,
                "coordinated_pairs": [],
                "unproven_pairs": [{
                    "entity_id": "switch.pump",
                    "automations": ["Stop for priority", "Resume after priority"],
                    "target_kind": "actuator",
                    "conflict_evidence": {
                        "kind": "opposite_or_different_deterministic_commands",
                        "intent_a": ["state:off"],
                        "intent_b": ["state:on"],
                    },
                }],
                "contradictory_deterministic_pairs": [{
                    "entity_id": "switch.pump",
                    "automations": ["Stop for priority", "Resume after priority"],
                }],
            },
            "dependency_graph": [
                {
                    "automation": "Stop for priority",
                    "controls": ["switch.pump", "input_boolean.priority_handoff"],
                    "triggers_on": [],
                },
                {
                    "automation": "Resume after priority",
                    "controls": ["switch.pump"],
                    "triggers_on": ["input_boolean.priority_handoff"],
                },
            ],
            "architecture_analysis": {},
            "findings": [{
                "rule_id": "HD-AUTO-003",
                "examples": [{
                    "entity_id": "switch.pump",
                    "unprotected_pairs": [["Stop for priority", "Resume after priority"]],
                }],
            }],
            "diagnostic_explanations": [],
        }
        by_alias = {
            "Stop for priority": [{"effective": {
                "trigger": [{"platform": "state", "entity_id": "sensor.priority", "to": "on"}],
                "action": [
                    {"service": "switch.turn_off", "target": {"entity_id": "switch.pump"}},
                    {"service": "input_boolean.turn_on", "target": {"entity_id": "input_boolean.priority_handoff"}},
                ],
            }}],
            "Resume after priority": [{"effective": {
                "trigger": [{"platform": "state", "entity_id": "input_boolean.priority_handoff", "to": "off"}],
                "action": [
                    {"service": "switch.turn_on", "target": {"entity_id": "switch.pump"}},
                ],
            }}],
        }
        try:
            semantics_v084.sem_v1.effective_automation_map = lambda _report: (by_alias, [])
            result = semantics_v084.build_condition_semantics_v4(report)
        finally:
            semantics_v084.sem_v1.effective_automation_map = original
        self.assertEqual(result["protocol_coordinated_pair_count"], 1)
        self.assertEqual(result["physical_unproven_pair_count"], 0)
        self.assertEqual(result["contradictory_deterministic_pair_count"], 0)
        self.assertEqual(result["protocol_coordinated_pairs"][0]["reason"], "helper_phase_handoff")

    def test_temporal_deescalated_is_not_resolved(self):
        now = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
        previous = datetime(2026, 8, 10, 9, 30, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.json"
            history.write_text(json.dumps([{
                "generated_at": iso(previous),
                "active_ids": ["DX-OVERKIZ"],
                "all_diagnostic_ids": ["DX-OVERKIZ"],
                "health_score_v4": 80,
            }]), encoding="utf-8")
            report = {
                "generated_at": iso(now),
                "diagnostic_explanations": [{"id": "DX-OVERKIZ", "source_type": "registry_cluster", "priority": "info"}],
                "action_plan": {"items": []},
                "recommendation_queue": {"items": []},
                "temporal_analysis": {},
                "privacy": {},
            }
            result = apply_temporal_v31(report, history_path=history)
            self.assertEqual(result["resolved_since_previous_count"], 0)
            self.assertEqual(result["deescalated_since_previous_count"], 1)
            self.assertIn("DX-OVERKIZ", result["deescalated_since_previous"])

    def test_non_plan_diagnostic_is_not_artificially_new(self):
        now = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.json"
            history.write_text(json.dumps([{
                "generated_at": "2026-08-10T09:30:00Z",
                "active_ids": [],
                "all_diagnostic_ids": [],
            }]), encoding="utf-8")
            report = {
                "generated_at": iso(now),
                "diagnostic_explanations": [{"id": "DX-INFO", "source_type": "finding", "priority": "info"}],
                "action_plan": {"items": []},
                "recommendation_queue": {"items": []},
                "temporal_analysis": {},
                "privacy": {},
            }
            apply_temporal_v31(report, history_path=history)
            self.assertEqual(report["diagnostic_explanations"][0]["temporal"]["status"], "observed_not_plan_tracked")

    def test_lineage_propagates_registry_source_to_derived_automation_dependency(self):
        old_root = scanner.CONFIG_ROOT
        try:
            with tempfile.TemporaryDirectory() as tmp:
                scanner.CONFIG_ROOT = Path(tmp)
                (Path(tmp) / "templates.yaml").write_text(
                    "- sensor:\n"
                    "    - name: Solar Power\n"
                    "      state: \"{{ states('sensor.inverter_power') | float(0) }}\"\n",
                    encoding="utf-8",
                )
                report = {
                    "dependency_graph": [{
                        "automation": "Use solar",
                        "triggers_on": [],
                        "controls": [],
                        "reads": ["sensor.solar_power"],
                        "calls": [],
                        "references": ["sensor.solar_power"],
                        "transitive_controls": [],
                        "transitive_calls": [],
                    }],
                    "dependency_graph_meta": {},
                    "architecture_analysis": {
                        "automation_risk_profiles": [{"automation": "Use solar", "risk_index": 10}],
                    },
                    "registry_analysis": {
                        "integration_health": {"groups": [{
                            "integration": "solar",
                            "affected_entities": ["sensor.inverter_power"],
                            "examples": [],
                        }]},
                        "device_health": {"groups": []},
                    },
                    "diagnostic_explanations": [{
                        "id": "DX-SOLAR",
                        "source_type": "registry_integration",
                        "source_id": "solar",
                    }],
                    "action_plan": {"items": [{"id": "DX-SOLAR"}]},
                    "recommendation_queue": {"items": [{"id": "DX-SOLAR"}]},
                    "root_cause_summary": {},
                    "privacy": {},
                    "diagnostic_engine": {},
                }
                lineage_v084.build_entity_lineage_v1(report)
                root = lineage_v084.apply_registry_lineage_blast_radius_v4(report)
                impact = report["diagnostic_explanations"][0]["dependency_impact"]
                self.assertGreaterEqual(report["entity_lineage"]["confirmed_edge_count"], 1)
                self.assertTrue(impact["lineage_used"])
                self.assertEqual(impact["impacted_automation_count"], 1)
                self.assertEqual(root["registry_impacted_automation_count"], 1)
        finally:
            scanner.CONFIG_ROOT = old_root

    def test_resilience_warning_becomes_non_scoring_action(self):
        report = {
            "resilience_analysis": {
                "items": [{
                    "entity_id": "sensor.grid_power",
                    "criticality": 93,
                    "automation_count": 3,
                    "explicit_guard_count": 1,
                    "numeric_default_only_count": 0,
                    "unprotected_count": 2,
                    "status": "partial",
                    "counts_as_external_spof": True,
                    "automation_evidence": [
                        {"automation": "A", "protection": "strong"},
                        {"automation": "B", "protection": "none"},
                        {"automation": "C", "protection": "none"},
                    ],
                }]
            },
            "findings": [],
            "diagnostic_explanations": [],
            "action_plan": {"items": [], "total": 0, "displayed": 0, "remaining": 0, "counts": {}},
            "recommendation_queue": {"items": [], "total": 0},
            "diagnostic_summary": {},
        }
        result = build_resilience_recommendations_v1(report)
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["scoring_applied"])
        self.assertEqual(report["action_plan"]["items"][0]["id"], "DX-HD-RES-001")
        self.assertEqual(report["action_plan"]["items"][0]["priority"], "verify")
        self.assertFalse(report["action_plan"]["items"][0]["dependency_impact"]["scoring_applied"])

    def test_consistency_v4_fails_on_stale_flow_counter(self):
        report = {
            "version": "0.8.4",
            "report_schema": {"version": "ha-doctor-report/0.8.4"},
            "action_plan": {"total": 0, "displayed": 0, "remaining": 0, "counts": {"action_now": 0, "verify": 0, "optimize": 0}, "items": []},
            "recommendation_queue": {"total": 0, "items": []},
            "diagnostic_summary": {"priority_counts": {"action_now": 0, "verify": 0, "optimize": 0}},
            "root_cause_summary": {"actionable_registry_incidents": 0},
            "flow_confidence": {"model": "flow_confidence_v3.1", "low_confidence_dynamic_edges": 0, "review_required_dynamic_edges": 0},
            "dependency_graph_meta": {"confidence_model": "flow_confidence_v3.1", "low_confidence_dynamic_edges": 45, "review_required_dynamic_edges": 0},
            "architecture_analysis": {"model": "architecture_v3_post_flow", "post_flow_recomputed": True},
            "temporal_analysis": {"resolved_since_previous": [], "deescalated_since_previous": []},
            "entity_lineage": {"parse_error_count": 0, "raw_yaml_persisted": False, "secret_values_persisted": False},
            "diagnostic_explanations": [],
            "score_meta": {"penalty_total": 0, "penalty_breakdown": []},
            "privacy": {},
        }
        result = validate_report_consistency_v4(report)
        self.assertEqual(result["status"], "fail")
        self.assertIn("flow.low_confidence_dynamic_edges", result["failures"])


if __name__ == "__main__":
    unittest.main()
