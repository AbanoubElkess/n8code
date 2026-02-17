from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.quantum_suite import default_quantum_suite, evaluate_suite_responses, score_quantum_answer


class TestQuantumSuite(unittest.TestCase):
    def test_suite_scoring(self) -> None:
        suite = default_quantum_suite()
        self.assertGreaterEqual(len(suite), 3)
        score = score_quantum_answer(
            "decoder tradeoff syndrome error rate latency",
            "Use decoder ablation to improve syndrome error rate and track tradeoff risk.",
        )
        self.assertGreater(score, 0.5)

    def test_suite_evaluation(self) -> None:
        suite = default_quantum_suite()
        answers = {case.case_id: "Provide falsification test and decoder tradeoff risk." for case in suite}
        results = evaluate_suite_responses(suite, answers)
        self.assertEqual(len(results), len(suite))
        self.assertTrue(all(0.0 <= r.score <= 1.0 for r in results))


if __name__ == "__main__":
    unittest.main()

