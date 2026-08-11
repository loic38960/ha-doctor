import unittest

from product_v110 import finding_evidence_count, _maintenance, _security, _single_snapshot_evidence
from sharing_v110 import build_share_report
from contracts_v110 import VERSION, REPORT_SCHEMA, SHARE_SCHEMA


class CrossValidatedEngineTests(unittest.TestCase):
    def test_finding_count_uses_full_examples_and_summary_total(self):
        self.assertEqual(finding_evidence_count({"examples": [{}, {}, {}]}), 3)
        self.assertEqual(finding_evidence_count({"summary": "29 entité(s) locales", "examples": [{}] * 12}), 29)
        self.assertEqual(finding_evidence_count({"example_count": 7}), 7)
        self.assertEqual(finding_evidence_count({"summary": "8 ligne(s) sensibles potentielles"}), 8)

    def test_security_and_maintenance_use_source_findings(self):
        report = {
            "findings": [
                {"rule_id": "HD-SEC-001", "examples": [{}, {}, {}]},
                {"rule_id": "HD-SEC-003", "examples": [{}] * 8},
                {"rule_id": "HD-CFG-001", "examples": [{}] * 7},
                {"rule_id": "HD-REG-002", "summary": "29 entité(s) locales", "examples": [{}] * 12},
                {"rule_id": "HD-CFG-005", "summary": "52/52"},
            ],
            "registry_analysis": {"orphan_analysis": {"candidate_count": 29}},
        }
        sec = _security(report)
        maint = _maintenance(report)
        self.assertEqual(sec["active_secret_hint_count"], 3)
        self.assertEqual(sec["archive_secret_hint_count"], 8)
        self.assertEqual(sec["posture"], "action_required")
        self.assertEqual(maint["missing_reference_count"], 7)
        self.assertEqual(maint["local_unavailable_review"], 29)

    def test_snapshot_evidence_reads_scan_performance(self):
        self.assertTrue(_single_snapshot_evidence({"scan_performance": {"single_state_snapshot_preserved": True}}))

    def test_share_preserves_controller_and_resilience_evidence(self):
        report = {
            "product": "HA Doctor",
            "version": VERSION,
            "generated_at": "2026-08-11T05:14:52Z",
            "scores": {"global": 76, "domains": {}},
            "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "findings": [],
            "action_plan": {"total": 0, "counts": {"action_now": 0, "verify": 0, "optimize": 0}, "items": []},
            "doctor_view": {"model": "doctor_view_v3_cross_validated", "trust": {"single_snapshot_evidence": True}, "next_best_actions": []},
            "product_intelligence": {
                "model": "product_intelligence_v3_cross_validated",
                "security": {"active_secret_hint_count": 3},
                "maintenance": {"missing_reference_count": 7},
                "controller_review_trace": {"model": "controller_review_trace_v1", "physical_pair_count": 1, "numeric_overlap_pair_count": 1, "items": [{"entity_id": "switch.boost", "automations": ["A", "B"], "reason": "overlap", "evidence_level": "hypothesis", "numeric_overlap_candidates": [{"entity_id": "sensor.level", "above": 98, "below": 100}], "templates_executed": False}]},
                "resilience_trace": {"model": "resilience_trace_v1", "must_fix_count": 1, "hardening_count": 0, "items": [{"entity_id": "sensor.pump", "tier": "must_fix", "unprotected_physical_automation_count": 1, "weak_physical_automation_count": 0, "risky_automations": ["Pool control"]}]},
                "cross_section_truth": {"single_snapshot_evidence": True},
            },
            "condition_semantics": {"unproven_pairs": []},
            "resilience_analysis": {},
            "resilience_recommendations": {"model": "resilience_recommendations_v3_exposure_first", "count": 1, "must_fix_count": 1, "hardening_count": 0, "items": [{"entity_id": "sensor.pump", "tier": "must_fix", "criticality": 32, "unprotected_physical_automation_count": 1, "weak_physical_automation_count": 0, "risky_automations": ["Pool control"]}]},
            "report_schema": {"version": REPORT_SCHEMA, "capabilities": []},
            "share_contract": {"schema": SHARE_SCHEMA},
            "self_check": {"status": "pass"},
        }
        payload = build_share_report(report)
        self.assertEqual(payload["version"], VERSION)
        self.assertEqual(payload["share_schema"]["version"], SHARE_SCHEMA)
        self.assertTrue(payload["controller_evidence"]["items"])
        self.assertEqual(payload["resilience"]["recommendations"]["items"][0]["risky_automations"], ["Pool control"])


if __name__ == "__main__":
    unittest.main()
