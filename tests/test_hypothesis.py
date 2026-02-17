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

    def test_explorer(self) -> None:
        explorer = HypothesisExplorer()
        seed = HypothesisProgram(rules=["Focus on coupling and noise."], priors={"consistency": 0.8})
        rules = explorer.propose_counterfactuals(seed, limit=4)
        self.assertEqual(len(rules), 4)
        ranked = explorer.rank(rules)
        self.assertEqual(len(ranked), 4)


if __name__ == "__main__":
    unittest.main()

