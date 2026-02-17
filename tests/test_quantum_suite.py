from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.quantum_suite import (
    adversarial_quantum_suite,
    default_quantum_suite,
    evaluate_suite_responses,
    holdout_quantum_suite,
    score_quantum_answer,
    suite_leakage_report,
)


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

    def test_adversarial_suite_present(self) -> None:
        adversarial = adversarial_quantum_suite()
        self.assertEqual(len(adversarial), 3)
        self.assertTrue(all(case.case_id.endswith("-A") for case in adversarial))

    def test_suite_leakage_report(self) -> None:
        report = suite_leakage_report()
        self.assertIn("public_vs_holdout", report)
        self.assertIn("public_vs_adversarial", report)
        self.assertIn("holdout_vs_adversarial", report)
        self.assertTrue(0.0 <= report["public_vs_holdout"]["mean_best_overlap"] <= 1.0)

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

    def test_evidence_keyword_section_is_ignored(self) -> None:
        expected = "stabilizer logical error rate runtime constraint testable"
        base_answer = (
            "Proposal:\n"
            "Adjust stabilizer schedule to lower logical error rate with runtime constraint checks.\n"
            "Risks:\n"
            "Risk: calibration drift can hide regressions.\n"
            "Next experiment:\n"
            "Run ablation and falsification on held-out channels."
        )
        with_evidence = (
            f"{base_answer}\n"
            "Evidence keywords:\n"
            "stabilizer, logical error rate, runtime constraint, testable, falsification, ablation"
        )
        self.assertAlmostEqual(
            score_quantum_answer(expected, base_answer),
            score_quantum_answer(expected, with_evidence),
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
