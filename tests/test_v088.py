import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import resilience_v088 as res
import semantics_v088 as sem
from sharing_v088 import HARD_BYTES, build_share_report


class ControllerSemanticsV6Tests(unittest.TestCase):
    def record(self, effective):
        return {"effective": effective}

    def test_literal_membership_guard_is_extracted(self):
        guards = sem.enhanced_required_state_guards({
            "condition": "template",
            "value_template": "{{ states('input_select.etats') in ['Été', 'Solaire', 'TurnOver'] }}",
        })
        self.assertEqual(guards["input_select.etats"], {"Été", "Solaire", "TurnOver"})

    def test_disjoint_membership_and_exact_state_resolve_exclusive(self):
        a = self.record({
            "condition": [{
                "condition": "template",
                "value_template": "{{ states('input_select.etats') in ['Été', 'Solaire', 'TurnOver'] }}",
            }],
            "action": [{"service": "switch.turn_off", "target": {"entity_id": "switch.pump"}}],
        })
        b = self.record({
            "condition": [{"condition": "state", "entity_id": "input_select.etats", "state": "Hiver"}],
            "action": [{"service": "switch.turn_on", "target": {"entity_id": "switch.pump"}}],
        })
        result = sem.resolve_pair_v6(a, b, "switch.pump")
        self.assertIsNotNone(result)
        self.assertEqual(result["proof_type"], "exclusive")

    def test_immediate_guarded_corrective_interlock_is_recognized(self):
        blocker = self.record({
            "trigger": [{"platform": "state", "entity_id": "switch.pump", "from": "off", "to": "on"}],
            "condition": [{"condition": "state", "entity_id": "input_boolean.priority", "state": "on"}],
            "action": [{"service": "switch.turn_off", "target": {"entity_id": "switch.pump"}}],
        })
        profile = sem.supervisory_interlock_profile(blocker, "switch.pump")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["trigger_state"], "on")
        self.assertEqual(profile["command_intent"], "state:off")
        self.assertEqual(profile["guards"]["input_boolean.priority"], ["on"])

    def test_blocker_and_normal_writer_resolve_as_interlock(self):
        blocker = self.record({
            "trigger": [{"platform": "state", "entity_id": "switch.pump", "to": "on"}],
            "condition": [{"condition": "state", "entity_id": "input_boolean.priority", "state": "on"}],
            "action": [{"service": "switch.turn_off", "target": {"entity_id": "switch.pump"}}],
        })
        writer = self.record({
            "condition": [{"condition": "state", "entity_id": "input_select.mode", "state": "Été"}],
            "action": [{"service": "switch.turn_on", "target": {"entity_id": "switch.pump"}}],
        })
        result = sem.resolve_pair_v6(blocker, writer, "switch.pump")
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "supervisory_interlock")

    def test_third_party_interlock_resolves_sender_and_writer(self):
        sender = self.record({
            "action": [
                {"service": "input_boolean.turn_on", "target": {"entity_id": "input_boolean.priority"}},
                {"service": "switch.turn_off", "target": {"entity_id": "switch.pump"}},
            ],
        })
        writer = self.record({
            "condition": [{"condition": "state", "entity_id": "input_select.mode", "state": "Été"}],
            "action": [{"service": "switch.turn_on", "target": {"entity_id": "switch.pump"}}],
        })
        blocker = self.record({
            "trigger": [{"platform": "state", "entity_id": "switch.pump", "to": "on"}],
            "condition": [{"condition": "state", "entity_id": "input_boolean.priority", "state": "on"}],
            "action": [{"service": "switch.turn_off", "target": {"entity_id": "switch.pump"}}],
        })
        result = sem.resolve_pair_v6(
            sender, writer, "switch.pump",
            all_records=[("sender", sender), ("writer", writer), ("blocker", blocker)],
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "mediated_supervisory_interlock")

    def test_two_uncoordinated_starters_remain_unresolved(self):
        a = self.record({"action": [{"service": "switch.turn_on", "target": {"entity_id": "switch.boost"}}]})
        b = self.record({"action": [{"service": "switch.turn_off", "target": {"entity_id": "switch.boost"}}]})
        self.assertIsNone(sem.resolve_pair_v6(a, b, "switch.boost"))


class ResilienceV4Tests(unittest.TestCase):
    def test_numeric_state_trigger_only_is_fail_closed(self):
        effective = {
            "trigger": [{"platform": "numeric_state", "entity_id": "sensor.grid", "below": -1000}],
            "action": [{"service": "switch.turn_on", "target": {"entity_id": "switch.boost"}}],
        }
        node = {
            "controls": ["switch.boost"],
            "triggers_on": ["sensor.grid"],
            "reads": [],
        }
        result = res.classify_automation_v4(effective, "sensor.grid", node)
        self.assertEqual(result["level"], "strong")
        self.assertEqual(result["kind"], "numeric_trigger_fail_closed")

    def test_validity_variable_gates_all_physical_branches(self):
        effective = {
            "variables": {
                "grid_entity": "sensor.grid",
                "all_ok": "{{ states(grid_entity) not in ['unknown','unavailable','none'] }}",
            },
            "action": [{
                "choose": [{
                    "conditions": [{"condition": "template", "value_template": "{{ all_ok }}"}],
                    "sequence": [{"service": "switch.turn_on", "target": {"entity_id": "switch.pump"}}],
                }],
            }],
        }
        node = {"controls": ["switch.pump"], "triggers_on": [], "reads": ["sensor.grid"]}
        result = res.classify_automation_v4(effective, "sensor.grid", node)
        self.assertEqual(result["level"], "strong")
        self.assertEqual(result["kind"], "availability_gate_on_all_physical_branches")

    def test_explicit_valid_and_invalid_branches_are_strong(self):
        effective = {
            "variables": {
                "grid_raw": "{{ states('sensor.grid') }}",
                "grid_valid": "{{ grid_raw not in ['unknown','unavailable','none'] }}",
            },
            "action": [{
                "choose": [
                    {
                        "conditions": [{"condition": "template", "value_template": "{{ not grid_valid }}"}],
                        "sequence": [{"service": "number.set_value", "target": {"entity_id": "number.limit"}, "data": {"value": 6}}],
                    },
                    {
                        "conditions": [{"condition": "template", "value_template": "{{ grid_valid }}"}],
                        "sequence": [{"service": "number.set_value", "target": {"entity_id": "number.limit"}, "data": {"value": 20}}],
                    },
                ],
            }],
        }
        node = {"controls": ["number.limit"], "triggers_on": [], "reads": ["sensor.grid"]}
        result = res.classify_automation_v4(effective, "sensor.grid", node)
        self.assertEqual(result["level"], "strong")
        self.assertEqual(result["kind"], "explicit_valid_invalid_control_branches")

    def test_observational_consumer_is_not_physical_risk(self):
        effective = {
            "action": [{"service": "script.turn_on", "target": {"entity_id": "script.notify"}}],
        }
        node = {"controls": [], "calls": ["script.notify"], "triggers_on": [], "reads": ["sensor.grid"]}
        result = res.classify_automation_v4(effective, "sensor.grid", node)
        self.assertFalse(result["risk_relevant"])
        self.assertEqual(result["role"], "observational")

    def test_observational_unprotected_does_not_prevent_protected_status(self):
        physical_effective = {
            "trigger": [{"platform": "numeric_state", "entity_id": "sensor.grid", "below": -1000}],
            "action": [{"service": "switch.turn_on", "target": {"entity_id": "switch.boost"}}],
        }
        observational_effective = {
            "action": [{"service": "script.turn_on", "target": {"entity_id": "script.notify"}}],
        }
        report = {
            "architecture_analysis": {"critical_dependencies": [{"entity_id": "sensor.grid", "criticality": 93}]},
            "dependency_graph": [
                {
                    "automation": "Physical",
                    "controls": ["switch.boost"],
                    "triggers_on": ["sensor.grid"],
                    "reads": [],
                    "references": ["sensor.grid"],
                },
                {
                    "automation": "Observe",
                    "controls": [],
                    "triggers_on": [],
                    "reads": ["sensor.grid"],
                    "references": ["sensor.grid"],
                },
            ],
        }
        analysis = res.build_resilience_analysis_v4(
            report,
            automation_map={
                "Physical": [{"effective": physical_effective}],
                "Observe": [{"effective": observational_effective}],
            },
        )
        item = analysis["items"][0]
        self.assertEqual(item["status"], "protected")
        self.assertEqual(item["unprotected_physical_automation_count"], 0)
        self.assertEqual(item["observational_consumer_count"], 1)

    def test_protected_analysis_removes_old_recommendation(self):
        report = {
            "resilience_analysis": {
                "items": [{
                    "entity_id": "sensor.grid",
                    "criticality": 93,
                    "counts_as_external_spof": True,
                    "status": "protected",
                    "unprotected_physical_automation_count": 0,
                    "weak_physical_automation_count": 0,
                }],
            },
            "findings": [{"rule_id": "HD-RES-001"}],
            "diagnostic_explanations": [{"id": "DX-HD-RES-001"}],
            "action_plan": {"items": [{"id": "DX-HD-RES-001"}]},
            "recommendation_queue": {"items": [{"id": "DX-HD-RES-001"}]},
        }
        result = res.build_resilience_recommendations_v2(report)
        self.assertEqual(result["count"], 0)
        self.assertFalse(any(item.get("rule_id") == "HD-RES-001" for item in report["findings"]))
        self.assertFalse(any(item.get("id") == "DX-HD-RES-001" for item in report["action_plan"]["items"]))


class DeliveryV088Tests(unittest.TestCase):
    def test_versions(self):
        import app_v088
        import intelligence_v088
        import scanner_v088
        import sharing_v088
        self.assertEqual(app_v088.VERSION, "0.8.8")
        self.assertEqual(intelligence_v088.VERSION, "0.8.8")
        self.assertEqual(scanner_v088.VERSION, "0.8.8")
        self.assertEqual(sharing_v088.VERSION, "0.8.8")

    def test_share_remains_bounded_and_exposes_v6_counters(self):
        report = {
            "product": "HA Doctor",
            "version": "0.8.8",
            "scores": {"global": 76},
            "findings": [{"rule_id": f"F{i}", "title": "Finding", "priority": "verify", "severity": "low", "domain": "automations", "summary": "x" * 300} for i in range(15)],
            "action_plan": {"total": 16, "counts": {"action_now": 3, "verify": 10, "optimize": 3}, "items": [{"id": f"D{i}", "title": "Action", "priority": "verify", "severity": "low", "domain": "automations"} for i in range(16)]},
            "diagnostic_explanations": [],
            "condition_semantics": {
                "semantic_v6_resolved_pair_count": 3,
                "membership_exclusive_pair_count": 1,
                "supervisory_interlock_pair_count": 1,
                "mediated_interlock_pair_count": 1,
                "unproven_pairs": [],
            },
            "controller_review_summary": {"entity_count": 1, "pair_count": 1, "physical_pair_count": 1, "helper_pair_count": 0, "semantic_v6_resolved_pair_count": 3},
            "resilience_analysis": {"model": res.MODEL, "protected_count": 2, "partial_count": 0, "review_count": 0, "items": []},
            "resilience_recommendations": {"count": 0, "items": []},
            "registry_analysis": {"integration_health": {"groups": []}, "device_health": {"groups": []}},
            "entity_health": {"unavailable": {}, "unknown": {}},
            "report_schema": {"version": "ha-doctor-report/0.8.8", "capabilities": []},
        }
        payload = build_share_report(report)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(encoded), HARD_BYTES)
        self.assertEqual(payload["version"], "0.8.8")
        self.assertEqual(payload["condition_semantics"]["semantic_v6_resolved_pair_count"], 3)
        self.assertEqual(payload["resilience"]["analysis"]["protected_count"], 2)

    def test_ui_contains_v088_markers(self):
        import app_v088
        source = (APP / "static" / "index.html").read_text(encoding="utf-8")
        enhanced = app_v088.enhance_ui_v088(source)
        self.assertIn("Control Intelligence 0.8.8", enhanced)
        self.assertIn("Calibration 0.8.8", enhanced)
        self.assertIn("Rapport à envoyer · compact", enhanced)


if __name__ == "__main__":
    unittest.main()
