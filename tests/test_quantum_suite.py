from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.quantum_suite import default_quantum_suite, evaluate_suite_responses, holdout_quantum_suite, score_quantum_answer


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

    def test_holdout_suite_present(self) -> None:
        holdout = holdout_quantum_suite()
        self.assertEqual(len(holdout), 3)
        self.assertTrue(all(case.case_id.endswith("-H") for case in holdout))

    def test_keyword_stuffing_penalty(self) -> None:
        expected = "decoder tradeoff syndrome error rate latency ablation"
        stuffed = "decoder decoder decoder syndrome syndrome tradeoff error rate ablation ablation decoder"
        balanced = (
            "Compare two decoder variants, report error-rate tradeoff and runtime latency, "
            "then run an ablation test with falsification."
        )
        stuffed_score = score_quantum_answer(expected, stuffed)
        balanced_score = score_quantum_answer(expected, balanced)
        self.assertLess(stuffed_score, balanced_score)


if __name__ == "__main__":
    unittest.main()
