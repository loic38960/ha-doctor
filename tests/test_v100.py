import unittest

import contracts_v100 as contracts
from product_v100 import apply_product_intelligence_v2, evidence_level
from resilience_v100 import build_resilience_recommendations_v3
from semantics_v100 import _ranges_overlap
from selfcheck_v100 import run_self_check_v2


class TestV100(unittest.TestCase):
    def test_contracts(self):
        self.assertEqual(contracts.VERSION, "0.10.0")
        self.assertEqual(contracts.REPORT_SCHEMA, "ha-doctor-report/0.10")
        self.assertEqual(contracts.SHARE_SCHEMA, "ha-doctor-share/4")
        self.assertLess(contracts.SHARE_TARGET_BYTES, contracts.SHARE_HARD_BYTES)

    def test_numeric_overlap_is_explainable_not_auto_resolved(self):
        overlap = _ranges_overlap(
            {"entity_id": "sensor.level", "above": 98.0, "below": None},
            {"entity_id": "sensor.level", "above": None, "below": 100.0},
        )
        self.assertTrue(overlap["overlap"])
        self.assertEqual(overlap["above"], 98.0)
        self.assertEqual(overlap["below"], 100.0)
        disjoint = _ranges_overlap(
            {"entity_id": "sensor.grid", "above": 650.0, "below": None},
            {"entity_id": "sensor.grid", "above": None, "below": -1000.0},
        )
        self.assertFalse(disjoint["overlap"])

    def test_resilience_prioritizes_real_unprotected_exposure(self):
        report = {
            "findings": [], "diagnostic_explanations": [],
            "action_plan": {"items": []}, "recommendation_queue": {"items": []},
            "resilience_analysis": {
                "items": [
                    {
                        "entity_id": "sensor.high_critical_weak", "counts_as_external_spof": True,
                        "criticality": 93, "automation_count": 10, "physical_control_consumer_count": 5,
                        "unprotected_physical_automation_count": 0, "weak_physical_automation_count": 1,
                        "automation_evidence": [{"automation": "Weak Controller", "risk_relevant": True, "protection": "weak"}],
                    },
                    {
                        "entity_id": "sensor.lower_critical_unprotected", "counts_as_external_spof": True,
                        "criticality": 32, "automation_count": 2, "physical_control_consumer_count": 2,
                        "unprotected_physical_automation_count": 1, "weak_physical_automation_count": 0,
                        "automation_evidence": [{"automation": "Unsafe Controller", "risk_relevant": True, "protection": "none"}],
                    },
                ]
            },
        }
        result = build_resilience_recommendations_v3(report)
        self.assertEqual(result["items"][0]["entity_id"], "sensor.lower_critical_unprotected")
        self.assertEqual(result["items"][0]["tier"], "must_fix")
        self.assertEqual(result["must_fix_count"], 1)
        self.assertEqual(result["hardening_count"], 1)

    def test_product_verdict_is_action_required_not_false_critical(self):
        report = {
            "product": "HA Doctor", "version": "0.8.8", "generated_at": "2026-08-10T12:00:00Z",
            "scores": {"global": 76, "domains": {"automations": 75}},
            "severity_counts": {"critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0},
            "findings": [{"rule_id": "HD-AUTO-009", "title": "Double writer", "severity": "high", "domain": "automations", "priority": "action_now"}],
            "action_plan": {"total": 1, "counts": {"action_now": 1, "verify": 0, "optimize": 0}, "items": [
                {"id": "DX-HD-AUTO-009", "title": "Double writer", "priority": "action_now", "severity": "high", "domain": "automations", "confidence": "high", "confidence_score": .97, "source_type": "finding", "source_id": "HD-AUTO-009"}
            ]},
            "score_v5_preview": {"v5_preview_score": 77, "why_lost_points": [{"id": "DX-HD-AUTO-009", "v5_penalty": 4.8}]},
            "quality_gates": {"overall": "pass", "gates": [{"key": "api", "status": "pass"}]},
            "consistency_analysis": {"status": "pass"},
            "flow_confidence": {"quality_status": "pass", "target_resolution_rate": 1.0, "unresolved_dynamic_targets": 0},
            "entity_lineage": {"parse_error_count": 0},
            "root_cause_summary": {"automation_coverage_ratio": 1.0, "actionable_registry_incidents": 0},
            "registry_analysis": {"available": True, "orphan_analysis": {}},
            "entity_health": {"unavailable": {"total": 0}, "unknown": {"total": 0}},
            "inventory": {"unavailable_count": 0, "unknown_count": 0, "automations_detected": 1},
            "condition_semantics": {"physical_unproven_pair_count": 0, "helper_unproven_pair_count": 0},
            "architecture_analysis": {"automation_count": 1, "closed_loop_count": 0},
            "temporal_analysis": {"score_delta": 0, "resolved_since_previous_count": 0},
            "report_schema": {"version": "ha-doctor-report/0.8.8", "capabilities": []},
            "privacy": {},
        }
        apply_product_intelligence_v2(report)
        self.assertEqual(report["doctor_view"]["verdict"]["code"], "action_required")
        self.assertEqual(report["diagnostic_summary"]["source"], "final_correlated_action_plan_v100")
        self.assertEqual(report["share_contract"]["target_bytes"], contracts.SHARE_TARGET_BYTES)
        self.assertEqual(evidence_level(report["action_plan"]["items"][0]), "confirmed")

    def test_selfcheck_detects_share_contract_drift(self):
        report = {
            "product": "HA Doctor", "version": contracts.VERSION, "generated_at": "2026-08-10T12:00:00Z",
            "report_schema": {"version": contracts.REPORT_SCHEMA},
            "scores": {"global": 90, "domains": {}},
            "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "findings": [], "action_plan": {"total": 0, "counts": {"action_now": 0, "verify": 0, "optimize": 0}, "items": []},
            "triage_board": {"total": 0, "items": [], "lane_counts": {"fix_now": 0}},
            "doctor_view": {"verdict": {"code": "healthy"}},
            "share_contract": {"schema": contracts.SHARE_SCHEMA, "model": contracts.SHARE_MODEL, "target_bytes": 32000, "hard_bytes": 36000, "single_source_of_truth": True},
            "condition_semantics": {"unproven_pair_count": 0, "physical_unproven_pair_count": 0, "helper_unproven_pair_count": 0, "unproven_pairs": [], "numeric_overlap_candidate_pair_count": 0},
            "resilience_analysis": {"items": [], "protected_count": 0, "partial_count": 0, "review_count": 0},
            "resilience_recommendations": {"items": [], "must_fix_count": 0, "hardening_count": 0},
            "flow_confidence": {"unresolved_dynamic_targets": 0},
            "temporal_analysis": {"rapid_rescans_promote_persistence": False},
            "product_intelligence": {"limitations": {"items": ["a", "b", "c", "d"]}, "safe_automatic_repairs": 0},
            "privacy": {"v100_additional_home_assistant_state_reads": 0},
            "consistency_analysis": {"status": "pass"},
        }
        result = run_self_check_v2(report)
        keys = {x["key"] for x in result["failures"]}
        self.assertIn("share_target_contract", keys)
        self.assertIn("share_hard_contract", keys)


if __name__ == "__main__":
    unittest.main()
