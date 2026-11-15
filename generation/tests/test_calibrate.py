"""Teste la logique du rapport de calibration avec des chiffres réels (pas de modèle nécessaire)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generation.calibrate import build_report  # noqa: E402


class TestReport(unittest.TestCase):
    def test_overlap_suggests_no_false_refusal(self):
        in_q = [f"q{i}" for i in range(5)]
        in_s = [0.825, 0.829, 0.846, 0.87, 0.93]
        off_q = ["maroc", "algerie", "japon"]
        off_s = [0.837, 0.835, 0.776]
        text, th = build_report("e5", "hybrid", in_q, in_s, off_q, off_s)
        self.assertEqual(th, 0.82)
        self.assertLess(th, min(in_s))
        self.assertIn("aucun faux refus", text)
        self.assertIn("maroc ; algerie", text)  # hors-sujet qui passent, listés
        self.assertIn("← suggéré", text)

    def test_separated_suggests_midpoint(self):
        text, th = build_report("e5", "hybrid", ["a", "b"], [0.85, 0.9], ["x"], [0.75])
        self.assertEqual(th, 0.8)
        self.assertIn("séparés", text)


if __name__ == "__main__":
    unittest.main()
