from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.hypothesis import FalsificationGate, HypothesisExplorer
from agai.types import HypothesisProgram


class TestHypothesis(unittest.TestCase):
    def test_falsification_gate(self) -> None:
        gate = FalsificationGate()
        good = gate.evaluate_rule("At temperature 12 mK, error rate can decrease by 9%.")
        bad = gate.evaluate_rule("Perpetual motion gives free infinite energy forever.")
        self.assertTrue(good.passed)
        self.assertFalse(bad.passed)
        self.assertTrue(len(bad.hard_failures) > 0)

    def test_explorer(self) -> None:
        explorer = HypothesisExplorer()
        seed = HypothesisProgram(rules=["Focus on coupling and noise."], priors={"consistency": 0.8})
        rules = explorer.propose_counterfactuals(seed, limit=4)
        self.assertEqual(len(rules), 4)
        ranked = explorer.rank(rules)
        self.assertEqual(len(ranked), 4)
        self.assertTrue(all(0.0 <= row.score <= 1.0 for row in ranked))

    def test_strict_gate_catches_causality_and_unbounded_claims(self) -> None:
        gate = FalsificationGate()
        invalid = gate.evaluate_rule(
            "Faster than light acausal transfer yields 250% gain with perfect fidelity compared to baseline."
        )
        self.assertFalse(invalid.passed)
        joined = " ".join(invalid.hard_failures).lower()
        self.assertIn("causality", joined)
        self.assertIn("out-of-range", joined)

    def test_sandbox_report_shape(self) -> None:
        explorer = HypothesisExplorer()
        seed = HypothesisProgram(rules=["Focus on stabilizer timing under drift."], priors={"consistency": 0.8})
        report = explorer.sandbox(seed_program=seed, limit=6, top_k=3)
        self.assertEqual(report["generated_count"], 6)
        self.assertIn("acceptance_rate", report)
        self.assertIn("family_coverage", report)
        self.assertIn("top_candidates", report)
        self.assertEqual(len(report["top_candidates"]), 3)
        self.assertGreaterEqual(report["rejected_count"], 1)


if __name__ == "__main__":
    unittest.main()
