import os
import tempfile
import unittest

from automation_resolution_v170 import _classify_feedback, build_duplicate_v2
from reference_intelligence_v170 import build_missing_reference_intelligence
from decision_v170 import _duplicate_resolution, _feedback_resolution, _reference_resolution
from temporal_v060 import save_history, load_history
from temporal_v170 import _attribution, stage_publication, commit_publication, validate_current_snapshot
from resilience_v170 import _normalize_pre_control
from sharing_v170 import build_share_report
from contracts_v170 import (
    VERSION, REPORT_SCHEMA, SHARE_SCHEMA, SHARE_TARGET_BYTES, SHARE_HARD_BYTES,
    ACTION_PLAN_MODEL, ACTION_PLAN_SOURCE, DECISION_MODEL, CONDITION_MODEL,
    TEMPORAL_MODEL, HISTORY_CONTRACT, REPAIR_PLAYBOOK_MODEL,
)


class ResolutionAttributionTests(unittest.TestCase):
    def test_specific_state_edge_opposite_action_is_terminating(self):
        profile = [{"platform": "state", "to": "on", "from": "off", "specific_state_edge": True}]
        classification, risk, review, reason = _classify_feedback(profile, {"state:on"}, {"state:off"})
        self.assertEqual(classification, "terminating_state_transition")
        self.assertEqual(risk, "low")
        self.assertFalse(review)
        self.assertEqual(reason, "specific_edge_requires_future_reentry")

    def test_broad_state_trigger_remains_review(self):
        profile = [{"platform": "state", "to": None, "from": None, "specific_state_edge": False}]
        classification, risk, review, _ = _classify_feedback(profile, set(), {"state:off"})
        self.assertEqual(classification, "self_retrigger_candidate")
        self.assertEqual(risk, "high")
        self.assertTrue(review)

    def test_exact_side_effect_duplicate_becomes_manual_fix_ready_only(self):
        report = {"duplicate_action_semantics": {
            "model": "duplicate_action_semantics_v1", "count": 1, "side_effect_duplicate_count": 1,
            "items": [{"automation": "A", "classification": "side_effect_duplicate", "exact_duplicate": True, "automatic_removal_safe": False}],
            "automatic_cleanup": False,
        }}
        dup = build_duplicate_v2(report)
        self.assertEqual(dup["manual_fix_ready_count"], 1)
        self.assertFalse(dup["automatic_cleanup"])
        item = {"source_id": "HD-AUTO-005", "operational_lane": "logic_review", "operational_relevance": "medium", "repair_playbook": {}}
        self.assertTrue(_duplicate_resolution(item, report))
        self.assertEqual(item["operational_lane"], "fix_now")
        self.assertEqual(item["resolution_status"], "manual_fix_ready")
        self.assertFalse(item["repair_playbook"]["automatic_fix"])
        self.assertEqual(item["repair_playbook"]["model"], REPAIR_PLAYBOOK_MODEL)

    def test_feedback_resolution_can_leave_logic_review(self):
        report = {"automation_feedback_semantics": {
            "model": "automation_feedback_v2_transition_proof", "count": 2,
            "review_count": 0, "statically_resolved_count": 2, "terminating_transition_count": 1,
            "runtime_loop_proven_count": 0,
        }}
        item = {"source_id": "HD-AUTO-008", "operational_lane": "logic_review", "operational_relevance": "medium", "repair_playbook": {}}
        self.assertTrue(_feedback_resolution(item, report))
        self.assertEqual(item["operational_lane"], "watch")
        self.assertEqual(item["resolution_status"], "statically_resolved")

    def test_missing_reference_intelligence_never_invents_replacement(self):
        report = {
            "findings": [{"rule_id": "HD-CFG-001", "examples": [
                {"entity_id": "light.missing_one", "file": "packages/test.yaml"},
                {"entity_id": "sensor.old_missing", "file": "archive/old.yaml"},
            ]}],
            "action_plan": {"items": [{"source_id": "HD-CFG-001", "dependency_impact": {"level": "low", "impacted_automation_count": 0}}]},
        }
        refs = build_missing_reference_intelligence(report)
        self.assertFalse(refs["replacement_inference_enabled"])
        self.assertGreaterEqual(refs["evidence_entity_count"], 2)
        for row in refs["items"]:
            self.assertFalse(row["replacement_inferred"])
            self.assertIsNone(row["replacement_suggestion"])
        item = {"source_id": "HD-CFG-001", "operational_lane": "logic_review", "operational_relevance": "medium", "repair_playbook": {}}
        self.assertTrue(_reference_resolution(item, report))
        self.assertEqual(item["operational_lane"], "watch")

    def test_resilience_native_weak_vs_unprotected(self):
        weak = _normalize_pre_control({"tier": "hardening", "phase_evidence": [{"phase": "pre_control_decision", "protection": "weak"}]})
        self.assertEqual(weak["tier"], "hardening")
        self.assertEqual(weak["pre_control_risk_count"], 0)
        self.assertEqual(weak["weak_pre_control_risk_count"], 1)
        unprotected = _normalize_pre_control({"tier": "hardening", "phase_evidence": [{"phase": "pre_control_decision", "protection": "none"}]})
        self.assertEqual(unprotected["tier"], "must_fix")
        self.assertEqual(unprotected["unprotected_pre_control_risk_count"], 1)

    def test_first_attribution_is_honest_when_old_baseline_lacks_domains(self):
        current = {"scores": {"global": 77, "domains": {"entities": 81, "automations": 75}}}
        previous = {"final_primary_score": 76, "publication_complete": True, "score_contract": HISTORY_CONTRACT}
        attr = _attribution(current, previous)
        self.assertEqual(attr["status"], "baseline_domain_detail_unavailable")
        self.assertFalse(attr["domain_detail_available"])
        self.assertEqual(attr["primary_delta"], 1)
        self.assertNotIn("changed_domains", attr)

    def test_next_attribution_uses_persisted_domain_scores(self):
        current = {"scores": {"global": 78, "domains": {"entities": 82, "automations": 75}}, "inventory_summary": {"unavailable_count": 180, "unknown_count": 150, "states": 1866}}
        previous = {
            "final_primary_score": 77, "publication_complete": True, "score_contract": HISTORY_CONTRACT,
            "domain_scores": {"entities": 81, "automations": 75},
            "inventory_signal": {"unavailable_count": 190, "unknown_count": 151, "states": 1866},
        }
        attr = _attribution(current, previous)
        self.assertEqual(attr["status"], "attributed")
        self.assertTrue(attr["domain_detail_available"])
        self.assertEqual(attr["largest_positive_domain"]["domain"], "entities")
        self.assertEqual(attr["largest_positive_domain"]["delta"], 1)
        self.assertEqual(attr["inventory_delta"]["unavailable_count"], -10)

    def test_published_v170_snapshot_stores_domain_scores(self):
        handle = tempfile.NamedTemporaryFile(delete=False); path=handle.name; handle.close(); os.unlink(path)
        try:
            save_history([{"generated_at":"2026-08-11T10:30:00Z","active_ids":[]}], path)
            report = {
                "generated_at":"2026-08-11T10:30:00Z","scores":{"global":77,"domains":{"entities":81,"automations":75}},
                "inventory_summary":{"unavailable_count":190,"unknown_count":151,"states":1866},
                "action_plan":{"model":ACTION_PLAN_MODEL},"diagnostic_summary":{"source":ACTION_PLAN_SOURCE},
                "decision_engine":{"model":DECISION_MODEL},"condition_semantics":{"model":CONDITION_MODEL},
                "temporal_analysis":{"model":TEMPORAL_MODEL},"self_check":{"status":"pass"},
            }
            stage_publication(report,path)
            self.assertTrue(validate_current_snapshot(report,path,require_published=False)["valid"])
            commit_publication(report,path)
            validated=validate_current_snapshot(report,path,require_published=True)
            self.assertTrue(validated["valid"])
            self.assertTrue(validated["domain_scores_persisted"])
            snap=load_history(path)[-1]
            self.assertEqual(snap["report_version"],VERSION)
            self.assertEqual(snap["report_schema"],REPORT_SCHEMA)
            self.assertEqual(snap["domain_scores"]["entities"],81)
        finally:
            if os.path.exists(path): os.unlink(path)

    def test_share_v11_keeps_identities_and_budget(self):
        actions=[]
        for i in range(16):
            actions.append({
                "id":f"A{i}","title":f"Action {i}","priority":"verify","severity":"low","domain":"test","confidence":"high",
                "source_type":"finding","source_id":f"F{i%15}","operational_lane":"logic_review","operational_relevance":"medium",
                "resolution_status":"logic_review_required","dependency_impact":{"level":"low","impacted_automation_count":0},
            })
        report={
            "generated_at":"2026-08-11T10:30:00Z","scores":{"global":77,"domains":{"entities":81}},"severity_counts":{},
            "inventory_summary":{"states":1866,"unavailable_count":190,"unknown_count":151},
            "findings":[{"rule_id":f"F{i}","title":f"Finding {i}","severity":"low","domain":"test","priority":"verify"} for i in range(15)],
            "action_plan":{"model":ACTION_PLAN_MODEL,"total":16,"items":actions},
            "diagnostic_summary":{"source":ACTION_PLAN_SOURCE,"plan_id_count":16,"top_actions":[]},
            "condition_semantics":{"model":CONDITION_MODEL,"unproven_pairs":[],"controller_pairs_analyzed":0,"resolved_pair_count":0,"physical_unproven_pair_count":0,"helper_unproven_pair_count":0},
            "controller_impact":{},
            "resilience_recommendations":{"model":"resilience_recommendations_v5_guard_actionable","analysis_model":"resilience_precision_v6_guard_actionable","items":[]},
            "automation_feedback_semantics":{"model":"automation_feedback_v2_transition_proof","count":0,"review_count":0,"runtime_loop_proven_count":0},
            "duplicate_action_semantics":{"model":"duplicate_action_semantics_v2_resolution_ready","count":0,"manual_fix_ready_count":0,"automatic_cleanup":False},
            "missing_reference_intelligence":{"model":"missing_reference_intelligence_v1","finding_present":False,"replacement_inference_enabled":False,"items":[]},
            "automation_resolution":{"model":"automation_resolution_v2"},
            "decision_engine":{"model":DECISION_MODEL,"total":16,"primary_action_count":16,"lane_counts":{"logic_review":16},"resolution_counts":{"logic_review_required":16},"canonical_order":{"model":"canonical_decision_order_v2_resolution","item_ids":[f"A{i}" for i in range(16)]}},
            "temporal_analysis":{"model":TEMPORAL_MODEL,"history_contract":HISTORY_CONTRACT},"score_attribution":{"model":"score_attribution_v1_domain_delta","status":"baseline_domain_detail_unavailable","domain_detail_available":False},
            "doctor_view":{"model":"doctor_view_v9_resolution_attribution","trust":{}},"product_intelligence":{"model":"x","public_contract_truth":{}},"quality_gates":{},"self_check":{"status":"pass"},"report_schema":{"version":REPORT_SCHEMA,"capabilities":[]},
        }
        share=build_share_report(report); meta=share["export_meta"]
        self.assertEqual(share["share_schema"]["version"],SHARE_SCHEMA)
        self.assertEqual(meta["exported_finding_count"],15)
        self.assertEqual(meta["exported_action_count"],16)
        self.assertTrue(meta["within_hard_bytes"])
        self.assertLessEqual(meta["share_report_bytes_estimate"],SHARE_TARGET_BYTES)


if __name__ == "__main__":
    unittest.main()
