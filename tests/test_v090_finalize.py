import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ha_doctor"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from finalize_v090 import VERSION, finalize_release


class FinalizeV090Tests(unittest.TestCase):
    def report(self, self_status="pass", quality="pass", trust=100):
        return {
            "doctor_view": {"verdict": {"label": "À traiter"}},
            "diagnostic_trust": {"score": trust, "level": "high", "deduction_reasons": []},
            "self_check": {"status": self_status, "check_count": 40, "pass_count": 40 if self_status == "pass" else 38, "warning_count": 1 if self_status == "warning" else 0, "failure_count": 1 if self_status == "fail" else 0},
            "quality_gates": {"overall": quality, "gates": [{"key": "legacy", "label": "Legacy", "status": quality, "detail": "x"}]},
            "report_schema": {"capabilities": []},
            "diagnostic_engine": {},
            "privacy": {},
        }

    def test_version(self):
        self.assertEqual(VERSION, "0.9.0")

    def test_clean_report_ready(self):
        report = self.report()
        result = finalize_release(report)
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["publishable"])
        self.assertEqual(report["quality_gates"]["model"], "quality_gates_v7_self_checked")
        self.assertIn("report_self_check", {x["key"] for x in report["quality_gates"]["gates"]})

    def test_self_check_failure_blocks_and_degrades_trust(self):
        report = self.report(self_status="fail")
        result = finalize_release(report)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["publishable"])
        self.assertLessEqual(report["diagnostic_trust"]["score"], 50)
        self.assertEqual(report["doctor_view"]["trust"]["level"], "low")

    def test_warning_stays_publishable_with_warning(self):
        report = self.report(self_status="warning")
        result = finalize_release(report)
        self.assertEqual(result["status"], "ready_with_warnings")
        self.assertTrue(result["publishable"])
        self.assertEqual(report["diagnostic_trust"]["score"], 95)


if __name__ == "__main__":
    unittest.main()
