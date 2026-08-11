import os
import tempfile
import unittest

from semantics_v160 import build_controller_impact_v2
from resilience_v160 import classify_dependency_phase
from automation_precision_v160 import _scan_duplicate_sequence, _feedback_class
from decision_v160 import canonical_order_key
from temporal_v060 import save_history, load_history
from temporal_v160 import stage_publication, commit_publication, validate_current_snapshot, refresh_published_baseline_visibility
from sharing_v160 import build_share_report
from contracts_v160 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE,
    DECISION_MODEL, CONDITION_MODEL, HISTORY_CONTRACT,
)


class EvidencePrecisionTests(unittest.TestCase):
    def test_controller_impact_uses_only_remaining_physical_scope(self):
        sem = {
            "unproven_pairs": [
                {"entity_id": "switch.boost", "automations": ["A", "B"], "target_kind": "actuator", "review_priority": "high"},
                {"entity_id": "input_boolean.guard", "automations": ["A", "C"], "target_kind": "helper", "review_priority": "low"},
                {"entity_id": "input_datetime.last_off", "automations": ["D", "E"], "target_kind": "helper", "review_priority": "low"},
            ]
        }
        impact = build_controller_impact_v2(sem)
        self.assertEqual(impact["physical_pair_count"], 1)
        self.assertEqual(impact["impacted_automation_count"], 2)
        self.assertEqual(impact["impacted_automations"], ["A", "B"])
        self.assertEqual(impact["target_entities"], ["switch.boost"])
        self.assertTrue(impact["broad_historical_blast_radius_not_used_for_priority"])

    def test_resilience_distinguishes_pre_and_post_action_reads(self):
        pre = {
            "conditions": [{"condition": "template", "value_template": "{{ states('sensor.power')|float(0) > 10 }}"}],
            "actions": [{"action": "switch.turn_on", "target": {"entity_id": "switch.pump"}}],
        }
        post = {
            "actions": [
                {"action": "switch.turn_on", "target": {"entity_id": "switch.pump"}},
                {"condition": "template", "value_template": "{{ states('sensor.power')|float(0) > 10 }}"},
            ]
        }
        self.assertEqual(classify_dependency_phase(pre, "sensor.power")["phase"], "pre_control_decision")
        self.assertEqual(classify_dependency_phase(post, "sensor.power")["phase"], "post_action_confirmation")

    def test_duplicate_notify_is_side_effect_duplicate(self):
        action = {"action": "notify.mobile_app_phone", "data": {"message": "Hello"}}
        items = _scan_duplicate_sequence([action, dict(action)], "Test")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["classification"], "side_effect_duplicate")
        self.assertFalse(items[0]["automatic_removal_safe"])

    def test_feedback_class_never_claims_runtime_loop(self):
        classification, risk = _feedback_class({"state:on"}, {"state:on"})
        self.assertEqual(classification, "state_reassertion_feedback")
        self.assertEqual(risk, "low")
        classification, risk = _feedback_class({"state:on"}, {"state:off"})
        self.assertEqual(classification, "state_transition_feedback")
        self.assertEqual(risk, "medium")

    def test_canonical_order_keeps_watch_last(self):
        rows = [
            {"id": "watch", "operational_lane": "watch", "operational_relevance": "low", "execution_priority_score": 99, "severity": "high", "confidence_score": 1.0},
            {"id": "fix", "operational_lane": "fix_now", "operational_relevance": "high", "execution_priority_score": 70, "severity": "medium", "confidence_score": .9},
            {"id": "logic", "operational_lane": "logic_review", "operational_relevance": "medium", "execution_priority_score": 80, "severity": "medium", "confidence_score": .8},
        ]
        rows.sort(key=canonical_order_key)
        self.assertEqual([x["id"] for x in rows], ["fix", "logic", "watch"])

    def test_publication_snapshot_is_stamped_v160(self):
        handle = tempfile.NamedTemporaryFile(delete=False); path = handle.name; handle.close(); os.unlink(path)
        try:
            save_history([{"generated_at": "2026-08-11T09:00:00Z", "active_ids": []}], path)
            report = {
                "generated_at": "2026-08-11T09:00:00Z", "scores": {"global": 76},
                "score_v5_preview": {"v5_preview_score": 77},
                "action_plan": {"model": ACTION_PLAN_MODEL}, "diagnostic_summary": {"source": ACTION_PLAN_SOURCE},
                "decision_engine": {"model": DECISION_MODEL}, "condition_semantics": {"model": CONDITION_MODEL},
                "self_check": {"status": "pass"},
            }
            stage_publication(report, path)
            self.assertTrue(validate_current_snapshot(report, path, require_published=False)["valid"])
            commit_publication(report, path)
            self.assertTrue(validate_current_snapshot(report, path, require_published=True)["valid"])
            visibility = refresh_published_baseline_visibility(report, path)
            self.assertTrue(visibility["current_committed_baseline"])
            snap = load_history(path)[-1]
            self.assertEqual(snap["report_version"], VERSION)
            self.assertEqual(snap["report_schema"], REPORT_SCHEMA)
            self.assertEqual(snap["score_contract"], HISTORY_CONTRACT)
            self.assertEqual(snap["final_primary_score"], 76)
        finally:
            if os.path.exists(path): os.unlink(path)

    def test_share_preserves_identity_and_budget_on_compact_report(self):
        report = {
            "generated_at": "2026-08-11T09:00:00Z", "scores": {"global": 76}, "severity_counts": {},
            "inventory_summary": {"states": 1866, "unavailable_count": 188, "unknown_count": 188},
            "findings": [{"rule_id": f"F{i}", "title": f"Finding {i}", "severity": "low", "domain": "test", "priority": "verify"} for i in range(15)],
            "action_plan": {"model": ACTION_PLAN_MODEL, "total": 16, "items": [
                {"id": f"A{i}", "title": f"Action {i}", "priority": "verify", "severity": "low", "domain": "test", "confidence": "high", "source_type": "finding", "source_id": f"F{i%15}", "operational_lane": "logic_review", "operational_relevance": "medium", "execution_priority_score": 50, "dependency_impact": {"level": "low", "impacted_automation_count": 0}}
                for i in range(16)
            ]},
            "diagnostic_summary": {"source": ACTION_PLAN_SOURCE, "plan_id_count": 16, "top_actions": []},
            "condition_semantics": {"model": CONDITION_MODEL, "unproven_pairs": [], "controller_pairs_analyzed": 0, "resolved_pair_count": 0, "physical_unproven_pair_count": 0, "helper_unproven_pair_count": 0},
            "controller_impact": {"model": "controller_impact_v2_unresolved_scope", "physical_pair_count": 0, "impacted_automation_count": 0},
            "resilience_recommendations": {"model": "resilience_recommendations_v4_phase_aware", "analysis_model": "resilience_precision_v5_phase_aware", "items": []},
            "duplicate_action_semantics": {"model": "duplicate_action_semantics_v1", "count": 0, "items": [], "automatic_cleanup": False},
            "automation_feedback_semantics": {"model": "automation_feedback_v1_intent_aware", "count": 0, "items": [], "runtime_loop_proven_count": 0},
            "decision_engine": {"model": DECISION_MODEL, "total": 16, "primary_action_count": 16, "lane_counts": {"logic_review": 16}, "canonical_order": {"model": "canonical_decision_order_v1", "item_ids": [f"A{i}" for i in range(16)]}, "top": []},
            "temporal_analysis": {"model": "temporal_v7_published_baseline_visibility", "history_contract": HISTORY_CONTRACT, "history_policy": "publication_complete_required_v1", "publication_model": "publication_transaction_v1"},
            "product_intelligence": {"model": "product_intelligence_v8_evidence_precision", "public_contract_truth": {}},
            "doctor_view": {"model": "doctor_view_v8_evidence_precision", "verdict": {}, "trust": {}},
            "quality_gates": {}, "self_check": {"status": "pass"}, "report_schema": {"version": REPORT_SCHEMA, "capabilities": []},
        }
        share = build_share_report(report)
        meta = share["export_meta"]
        self.assertEqual(share["share_schema"]["version"], SHARE_SCHEMA)
        self.assertEqual(meta["exported_finding_count"], 15)
        self.assertEqual(meta["exported_action_count"], 16)
        self.assertTrue(meta["within_hard_bytes"])


if __name__ == "__main__":
    unittest.main()
