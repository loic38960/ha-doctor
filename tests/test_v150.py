import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HD = ROOT / "ha_doctor"
if str(HD) not in sys.path:
    sys.path.insert(0, str(HD))

import contracts_v150 as c
import product_v150
import semantics_v150
import sharing_v150
import temporal_v150
from temporal_v060 import load_history, save_history


class V150Contracts(unittest.TestCase):
    def test_contracts(self):
        self.assertEqual(c.VERSION, "0.15.0")
        self.assertEqual(c.REPORT_SCHEMA, "ha-doctor-report/0.15")
        self.assertEqual(c.SHARE_SCHEMA, "ha-doctor-share/9")
        self.assertEqual(c.SHARE_TARGET_BYTES, 22000)
        self.assertEqual(c.PUBLICATION_MODEL, "publication_transaction_v1")
        self.assertEqual(c.CONDITION_MODEL, "condition_semantics_v10_event_window_policy")

    def test_public_truth_sees_installed_share_contract(self):
        r = {
            "version": c.VERSION,
            "report_schema": {"version": c.REPORT_SCHEMA},
            "share_contract": {"schema": c.SHARE_SCHEMA, "model": c.SHARE_MODEL},
            "diagnostic_summary": {"source": c.ACTION_PLAN_SOURCE},
            "action_plan": {"model": c.ACTION_PLAN_MODEL, "items": [{"id": "x"}]},
            "controller_review_summary": {"model": c.CONTROLLER_REVIEW_MODEL},
            "condition_semantics": {"model": c.CONDITION_MODEL},
            "temporal_analysis": {"model": c.TEMPORAL_MODEL, "history_policy": c.HISTORY_POLICY},
        }
        truth = product_v150._public_truth(r, {"model": c.DECISION_MODEL, "total": 1})
        self.assertTrue(truth["share_schema_fresh"])
        self.assertTrue(truth["share_model_fresh"])
        self.assertTrue(truth["evaluated_after_contract_install"])
        self.assertTrue(all(v for k, v in truth.items() if k.endswith("_fresh")))


class V150EventSemantics(unittest.TestCase):
    def test_trigger_metadata_marks_numeric_state_as_crossing(self):
        effective = {
            "trigger": [
                {"platform": "numeric_state", "id": "full", "entity_id": "sensor.water", "above": 98, "for": {"minutes": 2}},
                {"platform": "time", "id": "clock", "at": "15:30:00"},
            ]
        }
        meta = semantics_v150._trigger_metadata(effective)
        self.assertTrue(meta["full"]["crossing_semantics"])
        self.assertFalse(meta["clock"]["crossing_semantics"])
        self.assertEqual(meta["full"]["for"], {"minutes": 2})


class V150PublicationTransaction(unittest.TestCase):
    def setUp(self):
        f = tempfile.NamedTemporaryFile(delete=False)
        self.path = f.name
        f.close()
        os.unlink(self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def _report(self):
        return {
            "generated_at": "2026-08-11T08:30:00Z",
            "scores": {"global": 75},
            "score_v5_preview": {"v5_preview_score": 76},
            "report_schema": {"version": c.REPORT_SCHEMA},
            "action_plan": {"model": c.ACTION_PLAN_MODEL},
            "diagnostic_summary": {"source": c.ACTION_PLAN_SOURCE},
            "decision_engine": {"model": c.DECISION_MODEL},
            "condition_semantics": {"model": c.CONDITION_MODEL},
            "self_check": {"status": "pass"},
        }

    def test_stage_is_not_baseline_then_commit_is(self):
        save_history([{"generated_at": "2026-08-11T08:30:00Z", "active_ids": []}], self.path)
        r = self._report()
        staged = temporal_v150.stage_publication(r, history_path=self.path)
        self.assertTrue(staged["synced"])
        s = load_history(self.path)[-1]
        self.assertFalse(s["publication_complete"])
        self.assertNotIn("score_contract", s)
        self.assertNotIn("final_primary_score", s)
        self.assertTrue(temporal_v150.validate_current_snapshot(r, history_path=self.path, require_published=False)["valid"])

        committed = temporal_v150.commit_publication(r, history_path=self.path)
        self.assertTrue(committed["synced"])
        s = load_history(self.path)[-1]
        self.assertTrue(s["publication_complete"])
        self.assertEqual(s["score_contract"], c.HISTORY_CONTRACT)
        self.assertEqual(s["final_primary_score"], 75)
        self.assertTrue(temporal_v150.validate_current_snapshot(r, history_path=self.path, require_published=True)["valid"])

    def test_abort_revokes_canonical_fields(self):
        save_history([{"generated_at": "2026-08-11T08:30:00Z", "active_ids": []}], self.path)
        r = self._report()
        temporal_v150.stage_publication(r, history_path=self.path)
        temporal_v150.commit_publication(r, history_path=self.path)
        temporal_v150.abort_publication(r, history_path=self.path, reason="post_commit_validation_failed")
        s = load_history(self.path)[-1]
        self.assertFalse(s["publication_complete"])
        self.assertNotIn("score_contract", s)
        self.assertNotIn("final_primary_score", s)
        self.assertEqual(s["history_role"], "publication_candidate")


class V150Share(unittest.TestCase):
    def test_compact_inventory_drops_domains_and_examples(self):
        r = {
            "inventory_summary": {
                "states": 1866, "unavailable_count": 192, "unknown_count": 189,
                "domains": {"sensor": 892}, "unavailable_examples": ["sensor.x"] * 20,
                "unknown_examples": ["sensor.y"] * 20, "yaml_files_scanned": 324,
                "yaml_bytes_scanned": 4915468, "automations_detected": 52,
                "blueprints_detected": 12, "entity_references_detected": 422,
            }
        }
        compact = sharing_v150._inventory(r)
        self.assertNotIn("domains", compact)
        self.assertNotIn("unavailable_examples", compact)
        self.assertNotIn("unknown_examples", compact)
        self.assertEqual(compact["states"], 1866)


if __name__ == "__main__":
    unittest.main()
