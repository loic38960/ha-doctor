import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import product_v090 as product
import selfcheck_v090 as selfcheck
from sharing_v090 import HARD_BYTES, MODEL as SHARE_MODEL, build_markdown_summary, build_share_report


class ProductV090Tests(unittest.TestCase):
    def test_confidence_tiers(self):
        self.assertEqual(product.confidence_tier(.95), "A")
        self.assertEqual(product.confidence_tier(.80), "B")
        self.assertEqual(product.confidence_tier(.65), "C")
        self.assertEqual(product.confidence_tier(.40), "D")

    def test_customer_lanes(self):
        self.assertEqual(product.customer_lane({"priority": "action_now", "severity": "low"}), "fix_now")
        self.assertEqual(product.customer_lane({"priority": "verify", "severity": "medium"}), "investigate")
        self.assertEqual(product.customer_lane({"priority": "verify", "severity": "low"}), "review")
        self.assertEqual(product.customer_lane({"priority": "optimize", "severity": "low"}), "optimize")

    def test_risk_orders_urgent_above_optimization(self):
        urgent = {"priority": "action_now", "severity": "high", "confidence_score": .95, "dependency_impact": {"level": "high"}, "temporal": {"status": "persistent"}}
        optimize = {"priority": "optimize", "severity": "low", "confidence_score": .95, "dependency_impact": {"level": "none"}}
        self.assertGreater(product.risk_score(urgent), product.risk_score(optimize))

    def test_triage_uses_score_gain_and_keeps_all_actions(self):
        report = base_report()
        triage = product.build_triage_board(report)
        self.assertEqual(triage["total"], 3)
        self.assertEqual({x["id"] for x in triage["items"]}, {"DX-A", "DX-B", "DX-C"})
        by_id = {x["id"]: x for x in triage["items"]}
        self.assertEqual(by_id["DX-A"]["estimated_score_gain"], 4.5)
        self.assertEqual(triage["next_best_actions"][0]["id"], "DX-A")

    def test_product_layer_does_not_change_primary_score(self):
        report = base_report()
        before = report["scores"]["global"]
        product.apply_product_intelligence(report)
        self.assertEqual(report["scores"]["global"], before)
        self.assertEqual(report["version"], "0.9.0")
        self.assertEqual(report["report_schema"]["version"], "ha-doctor-report/0.9")
        self.assertFalse(report["doctor_view"]["automatic_fix"])

    def test_trust_is_high_on_clean_inputs(self):
        report = base_report()
        product.apply_product_intelligence(report)
        trust = report["diagnostic_trust"]
        self.assertEqual(trust["level"], "high")
        self.assertGreaterEqual(trust["score"], 85)

    def test_trust_degrades_on_quality_failure(self):
        report = base_report()
        report["quality_gates"]["overall"] = "fail"
        product.apply_product_intelligence(report)
        self.assertLess(report["diagnostic_trust"]["score"], 85)


class SelfCheckV090Tests(unittest.TestCase):
    def test_happy_report_passes(self):
        report = base_report()
        product.apply_product_intelligence(report)
        result = selfcheck.run_self_check(report)
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["failure_count"], 0)
        self.assertGreater(result["check_count"], 25)

    def test_duplicate_action_id_fails(self):
        report = base_report()
        report["action_plan"]["items"][1]["id"] = "DX-A"
        product.apply_product_intelligence(report)
        result = selfcheck.run_self_check(report)
        self.assertEqual(result["status"], "fail")
        self.assertIn("action_ids_unique", {x["key"] for x in result["failures"]})

    def test_controller_count_mismatch_fails(self):
        report = base_report()
        report["controller_review_summary"]["pair_count"] = 99
        product.apply_product_intelligence(report)
        result = selfcheck.run_self_check(report)
        self.assertEqual(result["status"], "fail")
        self.assertIn("controller_pair_identity", {x["key"] for x in result["failures"]})


class DeliveryV090Tests(unittest.TestCase):
    def test_versions(self):
        import app_v090
        import scanner_v090
        import sharing_v090
        self.assertEqual(app_v090.VERSION, "0.9.0")
        self.assertEqual(scanner_v090.VERSION, "0.9.0")
        self.assertEqual(sharing_v090.VERSION, "0.9.0")
        self.assertEqual(product.VERSION, "0.9.0")
        self.assertEqual(selfcheck.VERSION, "0.9.0")

    def test_share_v3_is_bounded_and_keeps_action_identities(self):
        report = base_report(big=True)
        product.apply_product_intelligence(report)
        selfcheck.run_self_check(report)
        payload = build_share_report(report)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(encoded), HARD_BYTES)
        self.assertEqual(payload["share_schema"]["model"], SHARE_MODEL)
        self.assertEqual(payload["share_schema"]["version"], "ha-doctor-share/3")
        self.assertEqual(
            {x["id"] for x in payload["action_plan"]["items"]},
            {x["id"] for x in report["action_plan"]["items"]},
        )
        self.assertFalse(payload["export_meta"]["raw_states_included"])
        self.assertIn("doctor_view", payload)
        self.assertIn("self_check", payload)

    def test_markdown_summary_is_human_readable(self):
        report = base_report()
        product.apply_product_intelligence(report)
        selfcheck.run_self_check(report)
        text = build_markdown_summary(report)
        self.assertIn("# Rapport HA Doctor", text)
        self.assertIn("Fix critical writer", text)
        self.assertIn("Auto-contrôle HA Doctor", text)
        self.assertNotIn("raw_states", text)

    def test_ui_contains_product_markers(self):
        import app_v090
        source = (APP / "static" / "index.html").read_text(encoding="utf-8")
        enhanced = app_v090.enhance_ui_v090(source)
        self.assertIn("HA Doctor 0.9 · Triage produit", enhanced)
        self.assertIn("Auto-contrôle 0.9", enhanced)
        self.assertIn("Résumé lisible", enhanced)
        self.assertIn("Rapport support · compact", enhanced)


def base_report(big=False):
    actions = [
        {
            "id": "DX-A", "title": "Fix critical writer", "priority": "action_now", "severity": "high",
            "domain": "automations", "confidence": "high", "confidence_score": .97,
            "source_type": "finding", "source_id": "HD-AUTO-009",
            "temporal": {"status": "persistent"},
            "dependency_impact": {"level": "medium", "impacted_automation_count": 2},
            "first_check": {"title": "Compare writers", "detail": "Open both automations"},
        },
        {
            "id": "DX-B", "title": "Check controller", "priority": "verify", "severity": "medium",
            "domain": "automations", "confidence": "medium", "confidence_score": .72,
            "source_type": "finding", "source_id": "HD-AUTO-003",
            "temporal": {"status": "persistent"},
            "dependency_impact": {"level": "high", "impacted_automation_count": 5},
        },
        {
            "id": "DX-C", "title": "Clean archive", "priority": "optimize", "severity": "low",
            "domain": "security", "confidence": "medium", "confidence_score": .76,
            "source_type": "finding", "source_id": "HD-SEC-003",
            "dependency_impact": {"level": "none", "impacted_automation_count": 0},
        },
    ]
    findings = [
        {"rule_id": "HD-AUTO-009", "title": "Writer", "severity": "high", "domain": "automations", "priority": "action_now", "summary": "x" * (1200 if big else 30), "examples": [{"entity_id": "input_number.a", "payload": "x" * 1000}] if big else []},
        {"rule_id": "HD-AUTO-003", "title": "Controller", "severity": "medium", "domain": "automations", "priority": "verify", "summary": "controller"},
        {"rule_id": "HD-SEC-003", "title": "Archive", "severity": "low", "domain": "security", "priority": "optimize", "summary": "archive"},
    ]
    report = {
        "product": "HA Doctor",
        "version": "0.8.8",
        "generated_at": "2026-08-10T12:30:00Z",
        "scores": {"global": 76, "domains": {"system": 100, "entities": 80, "automations": 75, "configuration": 89, "security": 85, "performance": 100}},
        "severity_counts": {"critical": 0, "high": 1, "medium": 1, "low": 1, "info": 0},
        "inventory": {"states": 100, "unavailable_count": 2, "unknown_count": 1, "yaml_files_scanned": 10, "automations_detected": 3},
        "findings": findings,
        "diagnostic_explanations": [{"id": "DX-A"}, {"id": "DX-B"}, {"id": "DX-C"}],
        "action_plan": {"model": "old", "total": 3, "counts": {"action_now": 1, "verify": 1, "optimize": 1}, "items": actions},
        "diagnostic_summary": {"plan_id_count": 3, "priority_counts": {"action_now": 1, "verify": 1, "optimize": 1, "info": 0}},
        "score_v5_preview": {"v5_preview_score": 77, "projected_after_top_3_fixes": 85, "applied_to_primary_score": False, "fix_scenarios": [{"id": "DX-A", "estimated_gain": 4.5}, {"id": "DX-B", "estimated_gain": 2.0}]},
        "quality_gates": {"overall": "pass", "counts": {"pass": 10}, "gates": []},
        "consistency_analysis": {"status": "pass", "failure_count": 0},
        "flow_confidence": {"quality_status": "pass", "target_resolution_rate": 1.0, "dynamic_target_resolution_rate": 1.0, "review_required_ratio": 0.0, "low_confidence_ratio": 0.0, "unresolved_dynamic_targets": 0},
        "condition_semantics": {"unproven_pair_count": 1, "unproven_pairs": [{"entity_id": "switch.pump", "automations": ["A", "B"], "target_kind": "actuator"}], "physical_unproven_pair_count": 1, "helper_unproven_pair_count": 0},
        "controller_review_summary": {"entity_count": 1, "pair_count": 1, "physical_pair_count": 1, "helper_pair_count": 0},
        "resilience_analysis": {"items": [{"entity_id": "sensor.grid", "counts_as_external_spof": True, "status": "protected"}], "protected_count": 1, "partial_count": 0, "review_count": 0},
        "resilience_recommendations": {"count": 0, "items": []},
        "temporal_analysis": {"new_count": 0, "persistent_count": 3, "recurrent_count": 0, "resolved_since_previous_count": 0, "deescalated_since_previous_count": 0},
        "regression_analysis": {"state": "stable", "score_delta": 0, "requires_attention": False},
        "registry_analysis": {"integration_health": {"groups": []}, "device_health": {"groups": []}},
        "entity_health": {"unavailable": {"total": 2, "groups": []}, "unknown": {"total": 1, "groups": []}},
        "entity_lineage": {"parse_error_count": 0, "confirmed_edge_count": 2},
        "privacy": {"automatic_configuration_changes": False, "state_snapshot_ephemeral": True},
        "diagnostic_engine": {"external_ai_used": False, "automatic_fix": False, "read_only": True},
        "report_schema": {"version": "ha-doctor-report/0.8.8", "backward_compatible_with": ["0.8.7"], "capabilities": []},
    }
    if big:
        report["dependency_graph"] = [{"automation": f"A{i}", "references": [f"sensor.x{j}" for j in range(300)]} for i in range(20)]
        report["architecture_analysis"] = {"top_hotspots": [{"entity_id": f"sensor.x{i}", "controllers": ["A"] * 20} for i in range(20)]}
    return report


if __name__ == "__main__":
    unittest.main()
