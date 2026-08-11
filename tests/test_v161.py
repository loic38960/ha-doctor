import unittest

from contracts_v160 import REPAIR_PLAYBOOK_MODEL
from hotfix_v161 import apply_hotfix_v161


class HotfixV161Tests(unittest.TestCase):
    def test_inherited_playbooks_are_normalized_without_changing_steps(self):
        report = {
            "decision_engine": {"items": [
                {"id": "A", "repair_playbook": {"model": "repair_playbook_v3", "repair_readiness": "needs_logic_review", "steps": [{"step": 1, "detail": "keep"}] }},
                {"id": "B", "repair_playbook": {"model": REPAIR_PLAYBOOK_MODEL, "repair_readiness": "ready_for_manual_change", "steps": [{"step": 1, "detail": "keep2"}] }},
            ]},
            "action_plan": {"items": [{"id": "A"}, {"id": "B"}]},
        }
        apply_hotfix_v161(report)
        for item in report["decision_engine"]["items"]:
            self.assertEqual(item["repair_playbook"]["model"], REPAIR_PLAYBOOK_MODEL)
            self.assertFalse(item["repair_playbook"]["automatic_fix"])
            self.assertTrue(item["repair_playbook"]["read_only"])
        self.assertEqual(report["decision_engine"]["items"][0]["repair_playbook"]["steps"][0]["detail"], "keep")
        self.assertEqual(report["action_plan"]["items"][0]["repair_playbook"]["model"], REPAIR_PLAYBOOK_MODEL)

    def test_weak_pre_control_stays_hardening_but_unprotected_stays_must_fix(self):
        report = {
            "resilience_recommendations": {
                "items": [
                    {
                        "entity_id": "sensor.pool_power",
                        "tier": "must_fix",
                        "phase_evidence": [{"phase": "pre_control_decision", "protection": "none"}],
                    },
                    {
                        "entity_id": "sensor.ecojoko",
                        "tier": "hardening",
                        "phase_evidence": [{"phase": "pre_control_decision", "protection": "weak"}],
                    },
                ]
            }
        }
        apply_hotfix_v161(report)
        pool, eco = report["resilience_recommendations"]["items"]
        self.assertEqual(pool["tier"], "must_fix")
        self.assertEqual(pool["pre_control_risk_count"], 1)
        self.assertEqual(pool["weak_pre_control_risk_count"], 0)
        self.assertEqual(eco["tier"], "hardening")
        self.assertEqual(eco["pre_control_risk_count"], 0)
        self.assertEqual(eco["weak_pre_control_risk_count"], 1)
        self.assertEqual(report["resilience_recommendations"]["must_fix_count"], 1)
        self.assertEqual(report["resilience_recommendations"]["hardening_count"], 1)


if __name__ == "__main__":
    unittest.main()
