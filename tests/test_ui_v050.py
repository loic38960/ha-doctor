import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "ha_doctor" / "static" / "index.html").read_text(encoding="utf-8")


class UIContractTests(unittest.TestCase):
    def test_version_is_injected_not_hardcoded(self):
        self.assertIn("__HA_DOCTOR_VERSION__", HTML)
        self.assertNotIn("Alpha 0.4", HTML)

    def test_v070_sections_are_rendered(self):
        for token in (
            "Verdict HA Doctor",
            "Plan d'action corrélé",
            "Causes racines",
            "Ce qui a changé",
            "Hotspots de dépendances",
            "Automatisations les plus complexes",
            "Intégrations & appareils",
            "Qualité & confidentialité",
            "Dette de maintenance",
            "action_plan",
            "diagnostic_explanations",
            "architecture_analysis",
            "regression_analysis",
        ):
            self.assertIn(token, HTML)

    def test_scan_state_and_read_only_language_remain_visible(self):
        self.assertIn("Analyse en cours", HTML)
        self.assertIn("Lecture seule", HTML)
        self.assertIn("Rapport anonymisé", HTML)
        self.assertIn("Aucun changement automatique", HTML)

    def test_ingress_api_paths_are_relative(self):
        self.assertIn("window.location.pathname", HTML)
        self.assertIn("ingressBase+'api/'", HTML)

    def test_six_main_views_exist(self):
        for view in ("overview", "actions", "architecture", "integrations", "history", "quality"):
            self.assertIn(f'id="view-{view}"', HTML)


if __name__ == "__main__":
    unittest.main()
