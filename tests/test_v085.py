import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import intelligence_v085
import semantics_v085_fixed as semantics
from consistency_v085 import validate_report_consistency_v5


class V085Tests(unittest.TestCase):
    def test_version_modules(self):
        import scanner_v085
        import intelligence_v085_fixed
        import app_v085
        self.assertEqual(scanner_v085.VERSION, "0.8.5")
        self.assertEqual(intelligence_v085.VERSION, "0.8.5")
        self.assertEqual(intelligence_v085_fixed.VERSION, "0.8.5")
        self.assertEqual(app_v085.VERSION, "0.8.5")

    def test_branch_helper_handoff_survives_global_multi_intent_helper(self):
        sender = {"effective": {
            "action": [{
                "choose": [
                    {
                        "conditions": [{"condition": "state", "entity_id": "switch.boost", "state": "off"}],
                        "sequence": [
                            {"service": "input_boolean.turn_on", "target": {"entity_id": "input_boolean.priority"}},
                            {"service": "switch.turn_off", "target": {"entity_id": "switch.pump"}},
                        ],
                    },
                    {
                        "conditions": [{"condition": "state", "entity_id": "switch.boost", "state": "on"}],
                        "sequence": [
                            {"service": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.priority"}},
                        ],
                    },
                ]
            }]
        }}
        receiver = {"effective": {
            "trigger": [{
                "platform": "state", "entity_id": "input_boolean.priority", "from": "on", "to": "off"
            }],
            "condition": [
                {"condition": "state", "entity_id": "input_boolean.priority", "state": "off"},
                {"condition": "state", "entity_id": "switch.pump", "state": "off"},
            ],
            "action": [
                {"service": "switch.turn_on", "target": {"entity_id": "switch.pump"}},
            ],
        }}
        result = semantics.resolve_branch_pair(sender, receiver, "switch.pump")
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "branch_phase_protocol")
        self.assertIn("branch_helper_phase_handoff", result["evidence"]["mechanisms"])

    def test_target_state_guard_alone_does_not_prove_controller_safety(self):
        stop = {"effective": {
            "condition": [{"condition": "state", "entity_id": "switch.boost", "state": "on"}],
            "action": [{"service": "switch.turn_off", "target": {"entity_id": "switch.boost"}}],
        }}
        start = {"effective": {
            "condition": [{"condition": "state", "entity_id": "switch.boost", "state": "off"}],
            "action": [{"service": "switch.turn_on", "target": {"entity_id": "switch.boost"}}],
        }}
        self.assertIsNone(semantics.resolve_branch_pair(stop, start, "switch.boost"))

    def test_build_semantics_removes_only_proven_branch_pair(self):
        original = semantics.base.sem_v1.effective_automation_map
        report = {
            "condition_semantics": {
                "resolved_pair_count": 2,
                "protocol_coordinated_pairs": [],
                "unproven_pairs": [
                    {"entity_id": "switch.pump", "automations": ["Stop", "Resume"], "target_kind": "actuator"},
                    {"entity_id": "switch.boost", "automations": ["Main", "Low"], "target_kind": "actuator"},
                ],
            },
            "findings": [{
                "rule_id": "HD-AUTO-003",
                "examples": [
                    {"entity_id": "switch.pump", "unprotected_pairs": [["Stop", "Resume"]], "unprotected_pair_count": 1},
                    {"entity_id": "switch.boost", "unprotected_pairs": [["Main", "Low"]], "unprotected_pair_count": 1},
                ],
            }],
            "diagnostic_explanations": [],
            "architecture_analysis": {},
        }
        records = {
            "Stop": [{"effective": {
                "action": [
                    {"service": "input_boolean.turn_on", "target": {"entity_id": "input_boolean.priority"}},
                    {"service": "switch.turn_off", "target": {"entity_id": "switch.pump"}},
                ],
            }}],
            "Resume": [{"effective": {
                "trigger": [{"platform": "state", "entity_id": "input_boolean.priority", "from": "on", "to": "off"}],
                "condition": [{"condition": "state", "entity_id": "input_boolean.priority", "state": "off"}],
                "action": [{"service": "switch.turn_on", "target": {"entity_id": "switch.pump"}}],
            }}],
            "Main": [{"effective": {
                "condition": [{"condition": "state", "entity_id": "switch.boost", "state": "on"}],
                "action": [{"service": "switch.turn_off", "target": {"entity_id": "switch.boost"}}],
            }}],
            "Low": [{"effective": {
                "condition": [{"condition": "state", "entity_id": "switch.boost", "state": "off"}],
                "action": [{"service": "switch.turn_on", "target": {"entity_id": "switch.boost"}}],
            }}],
        }
        try:
            semantics.base.sem_v1.effective_automation_map = lambda _report: (records, [])
            result = semantics.build_condition_semantics_v5(report)
        finally:
            semantics.base.sem_v1.effective_automation_map = original
        self.assertEqual(result["branch_protocol_resolved_pair_count"], 1)
        self.assertEqual(result["physical_unproven_pair_count"], 1)
        remaining = result["unproven_pairs"][0]
        self.assertEqual(remaining["entity_id"], "switch.boost")

    def _consistent_report(self):
        return {
            "version": "0.8.5",
            "report_schema": {"version": "ha-doctor-report/0.8.5"},
            "inventory": {"unavailable_count": 2, "unknown_count": 3},
            "entity_health": {"unavailable": {"total": 2}, "unknown": {"total": 3}},
            "action_plan": {"total": 0, "displayed": 0, "remaining": 0, "counts": {"action_now": 0, "verify": 0, "optimize": 0}, "items": []},
            "recommendation_queue": {"total": 0, "items": []},
            "diagnostic_summary": {"priority_counts": {"action_now": 0, "verify": 0, "optimize": 0}},
            "root_cause_summary": {"actionable_registry_incidents": 0},
            "flow_confidence": {"model": "flow_confidence_v3.1", "low_confidence_dynamic_edges": 0, "review_required_dynamic_edges": 0},
            "dependency_graph_meta": {"confidence_model": "flow_confidence_v3.1", "low_confidence_dynamic_edges": 0, "review_required_dynamic_edges": 0},
            "architecture_analysis": {
                "model": "architecture_v3_post_flow", "post_flow_recomputed": True,
                "shared_actuator_count": 4, "closed_loop_count": 1, "critical_dependency_count": 2,
            },
            "executive_summary": {"shared_actuator_count": 4, "closed_loop_count": 1, "critical_dependency_count": 2},
            "condition_semantics": {"unproven_pair_count": 0, "unproven_pairs": [], "physical_unproven_pair_count": 0},
            "temporal_analysis": {"resolved_since_previous": [], "deescalated_since_previous": []},
            "entity_lineage": {"parse_error_count": 0, "raw_yaml_persisted": False, "secret_values_persisted": False},
            "diagnostic_explanations": [],
            "findings": [],
            "score_meta": {"penalty_total": 0, "penalty_breakdown": []},
            "score_v5_preview": {"v5_preview_score_raw": 90.2, "v5_preview_score": 90, "projected_after_top_3_fixes": 90, "why_lost_points": []},
            "privacy": {},
        }

    def test_consistency_v5_detects_snapshot_drift(self):
        report = self._consistent_report()
        report["entity_health"]["unavailable"]["total"] = 3
        result = validate_report_consistency_v5(report)
        self.assertEqual(result["status"], "fail")
        self.assertIn("state_snapshot.unavailable_count", result["failures"])

    def test_consistency_v5_detects_stale_executive_architecture_count(self):
        report = self._consistent_report()
        report["executive_summary"]["shared_actuator_count"] = 2
        result = validate_report_consistency_v5(report)
        self.assertEqual(result["status"], "fail")
        self.assertIn("executive_summary.shared_actuator_count", result["failures"])

    def test_score_v5_preview_v2_is_usage_aware_but_non_destructive(self):
        report = {
            "scores": {"global": 80},
            "score_meta": {"penalty_total": 20, "penalty_breakdown": [{"id": "DX-OFFLINE", "title": "Offline", "penalty": 10}]},
            "diagnostic_explanations": [{
                "id": "DX-OFFLINE", "source_type": "registry_device", "source_id": "Device",
                "temporal": {"persistence_factor": 1.0},
                "dependency_impact": {"level": "none", "impacted_automation_count": 0},
            }],
        }
        # Keep the context-calibration lookup deterministic for this synthetic case.
        original = intelligence_v085.score_calibration._context_factor_for_id
        try:
            intelligence_v085.score_calibration._context_factor_for_id = lambda _report, _id: 1.0
            result = intelligence_v085.build_score_v5_preview_v2(report)
        finally:
            intelligence_v085.score_calibration._context_factor_for_id = original
        self.assertFalse(result["applied_to_primary_score"])
        self.assertEqual(result["why_lost_points"][0]["usage_factor"], 0.9)
        self.assertEqual(result["why_lost_points"][0]["v5_penalty"], 9.0)
        self.assertEqual(report["scores"]["global"], 80)


if __name__ == "__main__":
    unittest.main()
