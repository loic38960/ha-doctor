import unittest

import contracts_v130 as contracts
from semantics_v130 import disjoint_mandatory_guard_evidence
from decision_v130 import build_decision_engine, build_entity_attention_v2


class TestV130(unittest.TestCase):
    def test_contracts(self):
        self.assertEqual(contracts.VERSION, "0.13.0")
        self.assertEqual(contracts.REPORT_SCHEMA, "ha-doctor-report/0.13")
        self.assertEqual(contracts.SHARE_SCHEMA, "ha-doctor-share/7")
        self.assertEqual(contracts.HISTORY_CONTRACT, "published_primary_score_v1")
        self.assertEqual(contracts.DECISION_MODEL, "decision_engine_v1_evidence_playbooks")

    def test_mandatory_guard_disjoint_is_proof(self):
        proofs = disjoint_mandatory_guard_evidence(
            {"input_boolean.priority": {"on"}},
            {"input_boolean.priority": {"off"}},
        )
        self.assertEqual(len(proofs), 1)
        self.assertEqual(proofs[0]["entity_id"], "input_boolean.priority")
        self.assertEqual(proofs[0]["intersection"], [])

    def test_overlapping_guard_is_not_proof(self):
        proofs = disjoint_mandatory_guard_evidence(
            {"input_select.mode": {"eco", "auto"}},
            {"input_select.mode": {"auto", "boost"}},
        )
        self.assertEqual(proofs, [])

    def test_decision_engine_builds_manual_playbooks(self):
        report = {
            "action_plan": {"items": [
                {"id":"DX-HD-AUTO-009","title":"Double writer","priority":"action_now","severity":"high","source_type":"finding","source_id":"HD-AUTO-009","confidence":"high","confidence_score":0.97,"dependency_impact":{"level":"low","impacted_automation_count":0}},
                {"id":"DX-REG-INT-demo","title":"demo indisponible","priority":"verify","severity":"medium","source_type":"registry_integration","source_id":"demo","confidence":"high","confidence_score":0.92,"dependency_impact":{"level":"none","impacted_automation_count":0}},
            ]},
            "product_intelligence": {"entity_noise":{"raw_unavailable":10,"raw_unknown":5,"unavailable_attention":4,"unknown_attention":2,"registry_actionable_root_causes":1}},
            "root_cause_summary": {"actionable_registry_incidents":1},
        }
        decision = build_decision_engine(report)
        self.assertEqual(decision["total"], 2)
        self.assertEqual(decision["ready_for_manual_change_count"], 1)
        self.assertEqual(decision["external_dependency_count"], 1)
        first = next(x for x in decision["items"] if x["id"] == "DX-HD-AUTO-009")
        self.assertEqual(first["operational_relevance"], "high")
        self.assertFalse(first["repair_playbook"]["automatic_fix"])
        self.assertTrue(first["repair_playbook"]["steps"])
        external = next(x for x in decision["items"] if x["id"] == "DX-REG-INT-demo")
        self.assertEqual(external["operational_relevance"], "low")

    def test_entity_attention_separates_zero_impact_registry_noise(self):
        report = {
            "action_plan": {"items": [
                {"source_type":"registry_integration","dependency_impact":{"level":"none","impacted_automation_count":0}},
                {"source_type":"registry_device","dependency_impact":{"level":"medium","impacted_automation_count":2}},
                {"source_type":"finding","dependency_impact":{"level":"high","impacted_automation_count":3}},
            ]},
            "product_intelligence": {"entity_noise":{"raw_unavailable":193,"raw_unknown":191,"unavailable_attention":116,"unknown_attention":64,"registry_actionable_root_causes":6}},
        }
        attention = build_entity_attention_v2(report)
        self.assertEqual(attention["registry_actions"], 2)
        self.assertEqual(attention["registry_actions_without_automation_impact"], 1)
        self.assertEqual(attention["registry_actions_with_automation_impact"], 1)
        self.assertEqual(attention["high_dependency_diagnostic_count"], 1)
        self.assertEqual(attention["raw_attention_candidates"], 180)


if __name__ == "__main__":
    unittest.main()
