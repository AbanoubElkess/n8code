from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.reality_guard import RealityGuard


class TestRealityGuard(unittest.TestCase):
    def test_audit_text_detects_overclaim_terms(self) -> None:
        guard = RealityGuard()
        audit = guard.audit_text("This guarantee is perfect and unbeatable.")
        self.assertGreater(audit["overclaim_hits"], 0)
        self.assertIn(audit["risk_level"], {"medium", "high"})

    def test_audit_text_rewards_calibration_terms(self) -> None:
        guard = RealityGuard()
        conservative = guard.audit_text("Use baseline ablation with uncertainty bounds and confidence estimate.")
        hype = guard.audit_text("Guaranteed best frontier outcome always.")
        self.assertGreater(conservative["reality_score"], hype["reality_score"])

    def test_market_audit_shape(self) -> None:
        guard = RealityGuard()
        report = guard.audit_market_opportunities(
            [
                {
                    "key": "demo",
                    "description": "Baseline-first experiment with uncertainty reporting.",
                    "why_now": "Cost pressure is high.",
                    "first_experiment": "Run ablation against baseline.",
                }
            ]
        )
        self.assertIn("risk_counts", report)
        self.assertIn("rows", report)
        self.assertEqual(len(report["rows"]), 1)


if __name__ == "__main__":
    unittest.main()
