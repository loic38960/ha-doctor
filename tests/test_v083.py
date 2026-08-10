import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import scanner_v083
import semantics_v083
import resilience_v083
from consistency_v083 import validate_report_consistency_v3
from impact_v083 import _impact_for_entities
from intelligence_v083 import build_score_v5_preview
from temporal_v083 import apply_temporal_v3


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class V083Tests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(scanner_v083.VERSION, "0.8.3")

    def test_rapid_rescan_does_not_promote_persistence(self):
        now = datetime(2026, 8, 10, 8, 10, tzinfo=timezone.utc)
        previous = now - timedelta(seconds=30)
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.json"
            history.write_text(json.dumps([{
                "generated_at": iso(previous),
                "active_ids": ["DX-TEST"],
                "health_score_v4": 80,
            }]), encoding="utf-8")
            report = {
                "generated_at": iso(now),
                "diagnostic_explanations": [{
                    "id": "DX-TEST",
                    "source_type": "registry_device",
                    "temporal": {"consecutive_scans": 2},
                }],
                "action_plan": {"items": [{"id": "DX-TEST"}]},
                "recommendation_queue": {"items": [{"id": "DX-TEST"}]},
                "temporal_analysis": {},
                "privacy": {},
            }
            apply_temporal_v3(report, history_path=history)
            temporal = report["action_plan"]["items"][0]["temporal"]
            self.assertEqual(temporal["status"], "new")
            self.assertTrue(temporal["rapid_rescan_ignored"])
            self.assertEqual(temporal["qualified_observations"], 1)

    def test_current_legacy_snapshot_is_not_counted_as_previous_observation(self):
        now = datetime(2026, 8, 10, 8, 10, tzinfo=timezone.utc)
        previous = now - timedelta(seconds=30)
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.json"
            history.write_text(json.dumps([
                {"generated_at": iso(previous), "active_ids": ["DX-TEST"], "health_score_v4": 80},
                {"generated_at": iso(now), "active_ids": ["DX-TEST"], "health_score_v4": 80},
            ]), encoding="utf-8")
            report = {
                "generated_at": iso(now),
                "diagnostic_explanations": [{"id": "DX-TEST", "source_type": "registry_device"}],
                "action_plan": {"items": [{"id": "DX-TEST"}]},
                "recommendation_queue": {"items": [{"id": "DX-TEST"}]},
                "temporal_analysis": {},
                "privacy": {},
            }
            apply_temporal_v3(report, history_path=history)
            temporal = report["action_plan"]["items"][0]["temporal"]
            self.assertEqual(temporal["status"], "new")
            self.assertEqual(temporal["occurrences"], 2)
            self.assertEqual(temporal["qualified_observations"], 1)

    def test_elapsed_time_promotes_persistence(self):
        now = datetime(2026, 8, 10, 8, 30, tzinfo=timezone.utc)
        previous = now - timedelta(minutes=20)
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.json"
            history.write_text(json.dumps([{
                "generated_at": iso(previous),
                "active_ids": ["DX-TEST"],
                "health_score_v4": 80,
            }]), encoding="utf-8")
            report = {
                "generated_at": iso(now),
                "diagnostic_explanations": [{"id": "DX-TEST", "source_type": "registry_device"}],
                "action_plan": {"items": [{"id": "DX-TEST"}]},
                "recommendation_queue": {"items": [{"id": "DX-TEST"}]},
                "temporal_analysis": {},
                "privacy": {},
            }
            apply_temporal_v3(report, history_path=history)
            temporal = report["action_plan"]["items"][0]["temporal"]
            self.assertEqual(temporal["status"], "persistent")
            self.assertGreaterEqual(temporal["qualified_observations"], 2)

    def test_registry_blast_radius_uses_triggers_reads_and_risk(self):
        report = {
            "dependency_graph": [{
                "automation": "Critical automation",
                "triggers_on": ["sensor.grid_power"],
                "reads": ["sensor.grid_power"],
                "controls": ["switch.pump"],
                "references": ["sensor.grid_power", "switch.pump"],
                "calls": [],
                "transitive_controls": [],
                "transitive_calls": [],
            }],
            "architecture_analysis": {
                "automation_risk_profiles": [{
                    "automation": "Critical automation",
                    "risk_index": 25,
                }]
            },
        }
        result = _impact_for_entities(report, {"sensor.grid_power"})
        self.assertEqual(result["impacted_automation_count"], 1)
        self.assertEqual(result["high_risk_automation_count"], 1)
        self.assertGreater(result["weighted_impact_score"], 0)

    def test_flow_v3_promotes_literal_dynamic_target_and_does_not_warn_inferred_only(self):
        original = semantics_v083.sem_base.effective_automation_map
        report = {
            "dependency_graph": [{
                "automation": "Dynamic",
                "controls": ["climate.salon"],
                "dynamic_controls": [{"entity_id": "climate.salon", "confidence": 0.72}],
                "unresolved_dynamic_targets": [],
            }],
            "dependency_graph_meta": {
                "control_edges": 1,
                "target_resolution_rate": 1.0,
                "dynamic_target_resolution_rate": 1.0,
                "unresolved_dynamic_target_count": 0,
            },
        }
        try:
            semantics_v083.sem_base.effective_automation_map = lambda _report: ({
                "Dynamic": [{"effective": {
                    "action": [{
                        "service": "climate.set_temperature",
                        "target": {"entity_id": "climate.salon"},
                    }]
                }}]
            }, [])
            result = semantics_v083.build_flow_confidence_v3(report)
        finally:
            semantics_v083.sem_base.effective_automation_map = original
        self.assertEqual(result["literal_confirmed_promotions"], 1)
        self.assertEqual(result["dynamic_confidence_bands"]["high"], 1)
        self.assertEqual(result["quality_status"], "pass")

    def test_condition_v3_separates_physical_and_helper_pairs(self):
        original = semantics_v083.sem_base.effective_automation_map
        report = {
            "condition_semantics": {
                "resolved_pair_count": 2,
                "unproven_pairs": [
                    {"entity_id": "switch.pump", "automations": ["A", "B"]},
                    {"entity_id": "input_boolean.lock", "automations": ["C", "D"]},
                ],
            },
            "architecture_analysis": {},
            "findings": [],
            "diagnostic_explanations": [],
        }
        try:
            semantics_v083.sem_base.effective_automation_map = lambda _report: ({}, [])
            result = semantics_v083.build_condition_semantics_v3(report)
        finally:
            semantics_v083.sem_base.effective_automation_map = original
        self.assertEqual(result["physical_unproven_pair_count"], 1)
        self.assertEqual(result["helper_unproven_pair_count"], 1)

    def test_structured_state_guard_is_strong(self):
        effective = {
            "condition": [{
                "condition": "state",
                "entity_id": "sensor.grid_power",
                "state": "online",
            }]
        }
        result = resilience_v083.classify_fallback_v3(effective, "sensor.grid_power")
        self.assertEqual(result["level"], "strong")
        self.assertEqual(result["kind"], "structured_state_guard")

    def test_helper_is_not_external_spof(self):
        original = resilience_v083.effective_automation_map
        report = {
            "architecture_analysis": {
                "critical_dependencies": [{
                    "entity_id": "input_boolean.mode",
                    "criticality": 50,
                }]
            },
            "dependency_graph": [{
                "automation": "A",
                "references": ["input_boolean.mode"],
                "triggers_on": [],
                "reads": [],
            }],
        }
        try:
            resilience_v083.effective_automation_map = lambda _report: ({
                "A": [{"effective": {}}]
            }, [])
            result = resilience_v083.build_resilience_analysis_v3(report)
        finally:
            resilience_v083.effective_automation_map = original
        self.assertEqual(result["external_spof_count"], 0)
        self.assertEqual(result["configuration_dependency_count"], 1)
        self.assertEqual(result["review_count"], 0)

    def test_consistency_gate_detects_counter_mismatch(self):
        report = {
            "version": "0.8.3",
            "report_schema": {"version": "ha-doctor-report/0.8.3"},
            "action_plan": {
                "total": 99,
                "displayed": 1,
                "remaining": 0,
                "counts": {"action_now": 1, "verify": 0, "optimize": 0},
                "items": [{"id": "a", "priority": "action_now", "source_type": "finding"}],
            },
            "recommendation_queue": {
                "total": 1,
                "items": [{"id": "a", "priority": "action_now"}],
            },
            "diagnostic_summary": {"priority_counts": {"action_now": 1, "verify": 0, "optimize": 0}},
            "root_cause_summary": {"actionable_registry_incidents": 0},
            "score_meta": {"penalty_breakdown": [], "penalty_total": 0},
            "privacy": {},
        }
        result = validate_report_consistency_v3(report)
        self.assertEqual(result["status"], "fail")
        self.assertIn("action_plan.total", result["failures"])

    def test_score_v5_preview_explains_top_fixes_without_rewriting_primary(self):
        report = {
            "scores": {"global": 76},
            "score_meta": {
                "penalty_total": 24,
                "penalty_breakdown": [
                    {"id": "A", "title": "A", "penalty": 5},
                    {"id": "B", "title": "B", "penalty": 4},
                    {"id": "C", "title": "C", "penalty": 3},
                ],
            },
            "diagnostic_explanations": [
                {"id": "A", "source_type": "finding", "temporal": {"persistence_factor": 1}},
                {"id": "B", "source_type": "finding", "temporal": {"persistence_factor": 1}},
                {"id": "C", "source_type": "finding", "temporal": {"persistence_factor": 1}},
            ],
            "operational_context": {"diagnostics_deescalated": []},
            "registry_analysis": {"integration_health": {"groups": []}, "device_health": {"groups": []}},
        }
        result = build_score_v5_preview(report)
        self.assertEqual(report["scores"]["global"], 76)
        self.assertFalse(result["applied_to_primary_score"])
        self.assertGreater(result["projected_after_top_3_fixes"], result["v5_preview_score"])
        self.assertEqual(len(result["fix_scenarios"]), 3)


if __name__ == "__main__":
    unittest.main()
