import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "ha_doctor" / "static" / "index.html").read_text(encoding="utf-8")


class V050UIContractTests(unittest.TestCase):
    def test_version_is_injected_not_hardcoded(self):
        self.assertIn("__HA_DOCTOR_VERSION__", HTML)
        self.assertNotIn("Alpha 0.4", HTML)

    def test_explanatory_sections_are_rendered(self):
        for token in (
            "Verdict HA Doctor",
            "Plan d'action HA Doctor",
            "Causes racines : intégrations & appareils",
            "Observations volontairement tolérées",
            "diagnostic_explanations",
            "registry_observations",
            "action_plan",
        ):
            self.assertIn(token, HTML)

    def test_scan_state_and_read_only_language_remain_visible(self):
        self.assertIn("Analyse en cours", HTML)
        self.assertIn("Lecture seule et locale", HTML)
        self.assertIn("aucune IA externe", HTML)
        self.assertIn("aucune correction automatique", HTML)

    def test_ingress_api_paths_are_relative(self):
        self.assertIn("window.location.pathname", HTML)
        self.assertIn("ingressBase+'api/'", HTML)


if __name__ == "__main__":
    unittest.main()
