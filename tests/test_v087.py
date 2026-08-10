import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from hardening_v087 import harden_report_v087
from sharing_v087 import HARD_BYTES, build_share_report


class V087Tests(unittest.TestCase):
    def _report(self):
        controller_pairs = [
            {"entity_id": "switch.pump", "automations": ["A", "B"], "target_kind": "actuator"},
            {"entity_id": "switch.pump", "automations": ["A", "C"], "target_kind": "actuator"},
            {"entity_id": "switch.pump", "automations": ["D", "E"], "target_kind": "actuator"},
            {"entity_id": "switch.boost", "automations": ["F", "G"], "target_kind": "actuator"},
            {"entity_id": "input_boolean.phase", "automations": ["H", "I"], "target_kind": "helper"},
            {"entity_id": "input_boolean.phase", "automations": ["H", "J"], "target_kind": "helper"},
            {"entity_id": "input_datetime.last_off", "automations": ["K", "L"], "target_kind": "helper"},
        ]

        findings = []
        for i in range(15):
            priority = "action_now" if i < 3 else ("verify" if i < 13 else "optimize")
            findings.append({
                "rule_id": "HD-AUTO-003" if i == 3 else f"HD-{i:03d}",
                "title": "Controller conflict" if i == 3 else f"Finding {i}",
                "severity": "medium" if i < 13 else "low",
                "domain": "automations",
                "priority": priority,
                "summary": "Diagnostic summary " * 30,
                "recommendation": "Recommendation " * 30,
                "examples": [
                    {
                        "entity_id": f"sensor.example_{i}_{j}",
                        "automations": [f"Automation {i}", f"Automation {j}"],
                        "large": "x" * 800,
                    }
                    for j in range(6)
                ],
            })

        actions = []
        for i in range(15):
            priority = "action_now" if i < 3 else ("verify" if i < 13 else "optimize")
            actions.append({
                "id": "DX-HD-AUTO-003" if i == 3 else f"DX-HD-{i:03d}",
                "title": "Controller conflict" if i == 3 else f"Action {i}",
                "priority": priority,
                "severity": "medium",
                "domain": "automations",
                "confidence": "high",
                "confidence_score": 0.9,
                "source_type": "finding",
                "source_id": "HD-AUTO-003" if i == 3 else f"HD-{i:03d}",
                "first_check": {
                    "title": "Open configuration",
                    "detail": "Compare the relevant configuration " * 20,
                },
                "temporal": {
                    "status": "persistent",
                    "occurrences": 20,
                    "qualified_observations": 13,
                    "first_seen": "2026-08-08T00:00:00Z",
                    "last_seen_before_current": "2026-08-10T10:00:00Z",
                    "persistence_factor": 1.0,
                },
                "dependency_impact": {
                    "level": "low",
                    "impacted_automation_count": 0,
                    "high_risk_automation_count": 0,
                    "weighted_impact_score": 0.0,
                },
                "evidence": [{
                    "type": "summary",
                    "label": "Constat",
                    "text": "7 entité(s) ont plusieurs contrôleurs sans exclusivité clairement démontrée.",
                }],
            })

        # The real 0.8.6 report has 15 source findings but 16 plan items because
        # resilience contributes a correlated recommendation of its own.
        actions.append({
            "id": "DX-HD-RES-001",
            "title": "Dépendance externe critique insuffisamment protégée",
            "priority": "verify",
            "severity": "medium",
            "domain": "automations",
            "confidence": "high",
            "confidence_score": 0.9,
            "source_type": "finding",
            "source_id": "HD-RES-001",
            "first_check": {"title": "Check dependency", "detail": "Inspect explicit guards"},
            "dependency_impact": {"level": "high", "impacted_automation_count": 5},
        })

        return {
            "product": "HA Doctor",
            "version": "0.8.6",
            "generated_at": "2026-08-10T11:18:17Z",
            "scan_duration_seconds": 18.074,
            "scores": {"global": 76, "domains": {"automations": 75}},
            "severity_counts": {"critical": 0, "high": 2, "medium": 6, "low": 6, "info": 1},
            "home_assistant": {"version": "2026.8.1", "time_zone": "Europe/Paris", "components_count": 382},
            "supervisor": {"version": "2026.07.5", "healthy": True, "supported": True},
            "host": {"operating_system": "Home Assistant OS 18.2", "kernel": "6.18.39-haos"},
            "inventory": {
                "states": 1866,
                "unavailable_count": 215,
                "unknown_count": 155,
                "yaml_files_scanned": 324,
                "yaml_bytes_scanned": 4915468,
                "automations_detected": 52,
                "blueprints_detected": 12,
                "entity_references_detected": 422,
            },
            "diagnostic_summary": {
                "priority_counts": {"action_now": 3, "verify": 10, "optimize": 3},
                "actionable_count": 13,
                "headline": "3 corrections, 10 vérifications, 3 optimisations.",
                "source": "final_correlated_action_plan_v085",
                "plan_id_count": 16,
                "top_actions": [],
            },
            "executive_summary": {
                "health_score": 76,
                "health_label": "À surveiller",
                "text": "Summary",
                "root_cause_count": 6,
                "actionable_root_cause_count": 5,
                "detected_root_cause_count": 6,
                "complexity_score": 61,
                "complexity_label": "Avancée",
                "critical_dependency_count": 4,
            },
            "findings": findings,
            "action_plan": {
                "model": "correlated_action_plan_v3.2_branch_aware",
                "total": 16,
                "counts": {"action_now": 3, "verify": 10, "optimize": 3},
                "items": actions,
            },
            "diagnostic_explanations": [],
            "entity_health": {
                "unavailable": {"total": 215, "attention_count": 140, "groups": []},
                "unknown": {"total": 155, "stateful_count": 62, "attention_count": 31, "groups": []},
            },
            "registry_analysis": {
                "available": True,
                "entity_registry_count": 1791,
                "device_registry_count": 181,
                "integration_health": {"total": 52, "affected": 20, "offline": 2, "problematic": 7, "groups": []},
                "device_health": {"total": 181, "affected": 30, "offline": 6, "problematic": 9, "groups": []},
                "orphan_analysis": {"candidate_count": 29, "high_confidence_count": 0},
            },
            "dependency_graph": [
                {
                    "automation": f"Automation {i}",
                    "references": [f"sensor.entity_{j}" for j in range(500)],
                    "reads": [f"sensor.entity_{j}" for j in range(500)],
                }
                for i in range(40)
            ],
            "flow_confidence": {
                "model": "flow_confidence_v3.1",
                "target_resolution_rate": 1.0,
                "dynamic_target_resolution_rate": 1.0,
                "review_required_dynamic_edges": 0,
                "review_required_ratio": 0.0,
                "unresolved_dynamic_targets": 0,
                "quality_status": "pass",
            },
            "condition_semantics": {
                "model": "condition_semantics_v5_branch_protocols",
                "controller_pairs_analyzed": 20,
                "proven_exclusive_pair_count": 2,
                "coordinated_pair_count": 9,
                "resolved_pair_count": 13,
                "unproven_pair_count": 7,
                "physical_unproven_pair_count": 4,
                "helper_unproven_pair_count": 3,
                "other_unproven_pair_count": 0,
                "branch_protocol_resolved_pair_count": 2,
                "unproven_pairs": controller_pairs,
                "branch_protocol_resolved_pairs": [],
            },
            "architecture_analysis": {
                "model": "architecture_v3_post_flow",
                "complexity_score": 61,
                "complexity_label": "Avancée",
                "automation_count": 52,
                "entity_dependency_count": 166,
                "entity_edge_count": 314,
                "control_edge_count": 100,
                "call_edge_count": 20,
                "shared_actuator_count": 14,
                "critical_dependency_count": 4,
                "closed_loop_count": 3,
                "top_hotspots": [],
                "critical_dependencies": [],
            },
            "entity_lineage": {
                "model": "entity_lineage_v1",
                "edge_count": 197,
                "confirmed_edge_count": 18,
                "source_entity_count": 95,
                "derived_entity_count": 84,
                "known_entity_count": 354,
                "unresolved_output_count": 0,
                "parse_error_count": 0,
            },
            "resilience_analysis": {
                "model": "resilience_spof_v3",
                "critical_dependency_count": 4,
                "external_spof_count": 2,
                "partial_count": 2,
                "protected_count": 0,
                "items": [],
            },
            "resilience_recommendations": {"model": "resilience_recommendations_v1", "count": 1, "items": []},
            "root_cause_summary": {
                "actionable_registry_incidents": 5,
                "integration_incidents": 3,
                "device_incidents": 2,
                "detected_registry_incidents": 6,
            },
            "temporal_analysis": {
                "enabled": True,
                "model": "temporal_v3.1_plan_and_diagnostics",
                "scan_count": 20,
                "persistent_count": 16,
                "resolved_since_previous_count": 0,
            },
            "quality_gates": {
                "model": "quality_gates_v5_branch_aware",
                "overall": "warning",
                "counts": {"pass": 15, "warning": 2},
                "gates": [
                    {"key": "condition_semantics", "label": "Coordination", "status": "warning", "detail": "4 physical pairs"},
                    {"key": "resilience", "label": "Résilience", "status": "warning", "detail": "2 partial"},
                ],
            },
            "consistency_analysis": {
                "model": "consistency_gates_v5_cross_section",
                "status": "pass",
                "failure_count": 0,
                "warning_count": 0,
                "checks": {},
            },
            "score_v5_preview": {
                "model": "score_v5_preview_v2_usage_aware",
                "technical_v4_score": 76,
                "v5_preview_score": 77,
                "projected_after_top_3_fixes": 90,
                "why_lost_points": [],
                "fix_scenarios": [],
            },
            "score_meta": {"hardening_version": "0.8.5"},
            "report_schema": {
                "version": "ha-doctor-report/0.8.6",
                "backward_compatible_with": ["0.8.5"],
                "capabilities": ["assistant_share_report_v1"],
            },
        }

    def test_version_modules(self):
        import app_v087
        import hardening_v087
        import scanner_v087
        import sharing_v087

        self.assertEqual(app_v087.VERSION, "0.8.7")
        self.assertEqual(hardening_v087.VERSION, "0.8.7")
        self.assertEqual(scanner_v087.VERSION, "0.8.7")
        self.assertEqual(sharing_v087.VERSION, "0.8.7")

    def test_controller_review_counts_entities_and_pairs_separately(self):
        report = harden_report_v087(self._report())
        summary = report["controller_review_summary"]
        self.assertEqual(summary["pair_count"], 7)
        self.assertEqual(summary["entity_count"], 4)
        action = next(item for item in report["action_plan"]["items"] if item["source_id"] == "HD-AUTO-003")
        text = action["evidence"][0]["text"]
        self.assertIn("4 entité(s)", text)
        self.assertIn("7 paire(s)", text)
        self.assertNotIn("7 entité(s)", text)

    def test_hardening_is_non_destructive_for_primary_score(self):
        report = harden_report_v087(self._report())
        self.assertEqual(report["scores"]["global"], 76)
        self.assertEqual(report["version"], "0.8.7")
        self.assertEqual(report["score_meta"]["hardening_version"], "0.8.7")
        self.assertEqual(report["score_meta"]["share_report_model"], "assistant_share_report_v2")
        self.assertEqual(report["report_schema"]["version"], "ha-doctor-report/0.8.7")
        self.assertIn("assistant_share_report_v2", report["report_schema"]["capabilities"])

    def test_share_v2_is_hard_bounded_and_preserves_all_diagnostic_ids(self):
        report = harden_report_v087(self._report())
        payload = build_share_report(report)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(encoded), HARD_BYTES)
        self.assertEqual(payload["share_schema"]["model"], "assistant_share_report_v2")
        self.assertEqual(payload["share_schema"]["version"], "ha-doctor-share/2")
        self.assertNotIn("dependency_graph", payload)
        self.assertEqual(len(payload["findings"]), 15)
        self.assertEqual(len(payload["action_plan"]["items"]), 16)
        self.assertEqual(
            {item["id"] for item in payload["action_plan"]["items"]},
            {item["id"] for item in report["action_plan"]["items"]},
        )
        self.assertFalse(payload["export_meta"]["raw_states_included"])
        self.assertFalse(payload["export_meta"]["raw_yaml_included"])
        self.assertFalse(payload["export_meta"]["secret_values_included"])

    def test_ui_marks_compact_v2_share(self):
        import app_v087

        source = (APP / "static" / "index.html").read_text(encoding="utf-8")
        enhanced = app_v087.enhance_ui_v087(source)
        self.assertIn("Rapport à envoyer · compact", enhanced)
        self.assertIn("Partage 0.8.7", enhanced)
        self.assertIn("≤36 Ko", enhanced)
        self.assertIn("download-share", enhanced)


if __name__ == "__main__":
    unittest.main()
