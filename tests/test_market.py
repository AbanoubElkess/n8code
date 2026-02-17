from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.market import MarketGapAnalyzer


class TestMarket(unittest.TestCase):
    def test_market_report_shapes(self) -> None:
        analyzer = MarketGapAnalyzer()
        report = analyzer.report()
        self.assertIn("taxonomy", report)
        self.assertIn("competitive_map", report)
        self.assertIn("opportunities", report)
        self.assertIn("naming_reality", report)
        self.assertEqual(len(report["opportunities"]), 10)
        scores = [row["weighted_score"] for row in report["opportunities"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all("maturity_band" in row for row in report["opportunities"]))
        self.assertTrue(all("naming_risk_level" in row for row in report["opportunities"]))


if __name__ == "__main__":
    unittest.main()
