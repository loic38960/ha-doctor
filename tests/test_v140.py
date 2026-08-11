import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
APP = os.path.join(ROOT, "ha_doctor")
if APP not in sys.path:
    sys.path.insert(0, APP)

import contracts_v140 as c
import semantics_v140 as sem
import temporal_v140 as temporal
import decision_v140 as decision
import sharing_v140 as sharing


class TestV140PolicySemantics(unittest.TestCase):
    def test_numeric_policy_overlap_98_100(self):
        a = {"numeric": [{"entity_id": "sensor.water", "above": 98, "below": None}]}
        b = {"numeric": [{"entity_id": "sensor.water", "above": None, "below": 100}]}
        relation = sem._pair_numeric_relation(a, b)
        self.assertFalse(relation["disjoint"])
        self.assertEqual(relation["overlaps"][0]["above"], 98.0)
        self.assertEqual(relation["overlaps"][0]["below"], 100.0)

    def test_numeric_policy_disjoint_export_import(self):
        a = {"numeric": [{"entity_id": "sensor.grid", "above": 650, "below": None}]}
        b = {"numeric": [{"entity_id": "sensor.grid", "above": None, "below": -1000}]}
        relation = sem._pair_numeric_relation(a, b)
        self.assertTrue(relation["disjoint"])
        self.assertEqual(relation["disjoint"][0]["entity_id"], "sensor.grid")


class TestV140TemporalPublication(unittest.TestCase):
    def test_blocked_contract_snapshot_is_never_trusted(self):
        status = temporal._snapshot_status({
            "score_contract": c.HISTORY_CONTRACT,
            "final_primary_score": 75,
            "publication_complete": False,
        })
        self.assertFalse(status["trusted"])
        self.assertEqual(status["status"], "blocked_unpublished")

    def test_published_contract_snapshot_is_trusted(self):
        status = temporal._snapshot_status({
            "score_contract": c.HISTORY_CONTRACT,
            "final_primary_score": 75,
            "publication_complete": True,
        })
        self.assertTrue(status["trusted"])
        self.assertEqual(status["score"], 75)

    def test_blocked_current_sync_removes_canonical_contract(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            from temporal_v060 import save_history, load_history
            save_history([{
                "generated_at": "2026-08-11T06:29:37Z",
                "score_contract": c.HISTORY_CONTRACT,
                "final_primary_score": 75,
                "publication_complete": True,
            }], path)
            report = {
                "generated_at": "2026-08-11T06:29:37Z", "scores": {"global": 75},
                "score_v5_preview": {"v5_preview_score": 76},
                "action_plan": {"model": c.ACTION_PLAN_MODEL},
                "diagnostic_summary": {"source": c.ACTION_PLAN_SOURCE},
                "decision_engine": {"model": c.DECISION_MODEL},
                "condition_semantics": {"model": c.CONDITION_MODEL},
                "self_check": {"status": "fail"},
            }
            temporal.sync_publication_history(report, history_path=path, publication_complete=False)
            snap = load_history(path)[-1]
            self.assertNotIn("score_contract", snap)
            self.assertNotIn("final_primary_score", snap)
            self.assertFalse(snap["publication_complete"])
        finally:
            os.unlink(path)


class TestV140DecisionLanes(unittest.TestCase):
    def test_zero_impact_registry_goes_to_watch(self):
        item = {
            "source_type": "registry_integration", "source_id": "music_assistant",
            "priority": "verify", "dependency_impact": {"level": "none", "impacted_automation_count": 0},
        }
        lane = decision._operational_lane(item)
        self.assertEqual(lane, "watch")
        self.assertEqual(decision._operational_relevance(item, lane), "low")

    def test_impacted_registry_is_restore_if_needed(self):
        item = {
            "source_type": "registry_integration", "source_id": "huawei_solar",
            "priority": "verify", "dependency_impact": {"level": "low", "impacted_automation_count": 1},
        }
        lane = decision._operational_lane(item)
        self.assertEqual(lane, "restore_if_needed")


class TestV140Share(unittest.TestCase):
    def _report(self):
        findings = [
            {"rule_id": f"HD-X-{i:03d}", "title": f"Finding {i}", "severity": "low", "domain": "configuration", "priority": "verify", "example_count": 1}
            for i in range(15)
        ]
        actions = []
        decision_items = []
        for i in range(17):
            action = {
                "id": f"DX-{i:03d}", "title": f"Action {i}", "priority": "verify", "severity": "low",
                "domain": "configuration", "confidence": "high", "confidence_score": .9,
                "source_type": "finding", "source_id": f"HD-X-{i:03d}",
                "dependency_impact": {"level": "none", "impacted_automation_count": 0},
                "operational_lane": "logic_review", "operational_relevance": "medium", "execution_priority_score": 50,
            }
            actions.append(action)
            decision_items.append({
                **action,
                "repair_playbook": {
                    "model": c.REPAIR_PLAYBOOK_MODEL, "repair_readiness": "needs_logic_review", "category": "test",
                    "steps": [{"step": 1, "detail": "Check the evidence before changing anything."}],
                    "success_criteria": ["Diagnostic resolved or explicitly classified."],
                    "automatic_fix": False, "read_only": True,
                },
            })
        return {
            "version": c.VERSION, "generated_at": "2026-08-11T07:00:00Z", "scan_duration_seconds": 18.0,
            "scores": {"global": 75}, "severity_counts": {"high": 2},
            "inventory_summary": {"states": 1866, "unavailable_count": 192, "unknown_count": 189},
            "diagnostic_summary": {"source": c.ACTION_PLAN_SOURCE, "plan_id_count": 17, "priority_counts": {"verify": 17}},
            "executive_summary": {"health_score": 75, "health_label": "À surveiller"},
            "findings": findings,
            "action_plan": {"model": c.ACTION_PLAN_MODEL, "total": 17, "counts": {"verify": 17}, "items": actions},
            "condition_semantics": {"model": c.CONDITION_MODEL, "controller_pairs_analyzed": 20, "resolved_pair_count": 19, "unproven_pair_count": 1, "physical_unproven_pair_count": 1, "helper_unproven_pair_count": 0, "policy_overlap_pair_count": 1, "unproven_pairs": [{"entity_id": "switch.test", "automations": ["A", "B"], "target_kind": "actuator", "v9_policy_analysis": {"status": "policy_overlap", "conflict_path_pair_count": 1, "conflicts": [{"intent_a": "state:off", "intent_b": "state:on", "overlap_evidence": [{"entity_id": "sensor.water", "above": 98, "below": 100}]}], "simultaneous_execution_proven": False}}]},
            "resilience_analysis": {}, "resilience_recommendations": {"items": []},
            "quality_gates": {"overall": "warning", "counts": {"warning": 1}, "non_pass_gates": []},
            "doctor_view": {"model": c.PRODUCT_MODEL, "verdict": {"code": "action_required", "label": "Corrections prioritaires"}, "automatic_fix": False, "trust": {"read_only": True}},
            "self_check": {"model": c.SELF_CHECK_MODEL, "status": "pass"},
            "product_intelligence": {"model": "product_intelligence_v6_consolidated_decision", "security": {}, "maintenance": {}, "entity_attention": {}, "public_contract_truth": {}},
            "decision_engine": {"model": c.DECISION_MODEL, "total": 17, "items": decision_items, "top": decision_items[:8], "lane_counts": {"logic_review": 17}, "repair_readiness_counts": {"needs_logic_review": 17}, "operational_relevance_counts": {"medium": 17}, "repair_batches": {"logic_review": [x["id"] for x in decision_items]}, "entity_attention": {}},
            "temporal_analysis": {"model": c.TEMPORAL_MODEL, "history_contract": c.HISTORY_CONTRACT, "history_policy": c.HISTORY_POLICY, "score_comparison_status": "baseline", "previous_score_trusted": False, "current_primary_score": 75, "score_delta": None, "blocked_reports_never_become_score_baselines": True},
            "report_schema": {"version": c.REPORT_SCHEMA, "capabilities": []},
        }

    def test_share_keeps_all_identities_under_hard_bound(self):
        report = self._report()
        payload = sharing.build_share_report(report)
        self.assertEqual(payload["export_meta"]["exported_finding_count"], 15)
        self.assertEqual(payload["export_meta"]["exported_action_count"], 17)
        self.assertTrue(payload["export_meta"]["within_hard_bytes"])
        self.assertLessEqual(payload["export_meta"]["share_report_bytes_estimate"], c.SHARE_HARD_BYTES)
        self.assertEqual(payload["condition_semantics"]["policy_overlap_pair_count"], 1)


if __name__ == "__main__":
    unittest.main()
