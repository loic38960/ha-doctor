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
            "Plan d'action corrélé",
            "Causes racines",
            "Tolérés comme transitoires",
            "diagnostic_explanations",
            "registry_observations",
            "action_plan",
            "Évolution dans le temps",
        ):
            self.assertIn(token, HTML)

    def test_scan_state_and_read_only_language_remain_visible(self):
        self.assertIn("Analyse en cours", HTML)
        self.assertIn("Lecture seule, locale et historisée", HTML)
        self.assertIn("Rapport anonymisé", HTML)
        self.assertIn("Aucune correction automatique", HTML)

    def test_ingress_api_paths_are_relative(self):
        self.assertIn("window.location.pathname", HTML)
        self.assertIn("ingressBase+'api/'", HTML)


if __name__ == "__main__":
    unittest.main()
