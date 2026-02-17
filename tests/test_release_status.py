from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.release_status import ReleaseStatusEvaluator


class TestReleaseStatusEvaluator(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-release-status-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_internal_ready_without_external_claim(self) -> None:
        evaluator = ReleaseStatusEvaluator(policy_path="config/repro_policy.json")
        report = evaluator.evaluate(
            {
                "benchmark_progress": {
                    "ready": True,
                    "gaps": {"remaining_distance": 0.0},
                },
                "declared_baseline_comparison": {
                    "summary": {"comparable_baselines": 0}
                },
                "moonshot_tracking": {
                    "summary": {"best_signal": 0.1}
                },
            }
        )
        self.assertTrue(report["release_ready_internal"])
        self.assertFalse(report["external_claim_ready"])
        self.assertEqual(report["claim_scope"], "internal-comparative-only")
        self.assertTrue(report["gates"]["hard_suite_gate"]["pass"])

    def test_not_ready_when_hard_suite_gate_fails(self) -> None:
        evaluator = ReleaseStatusEvaluator(policy_path="config/repro_policy.json")
        report = evaluator.evaluate(
            {
                "benchmark_progress": {
                    "ready": False,
                    "gaps": {"remaining_distance": 0.42},
                },
                "declared_baseline_comparison": {
                    "summary": {"comparable_baselines": 1}
                },
            }
        )
        self.assertFalse(report["release_ready_internal"])
        self.assertEqual(report["claim_scope"], "not-ready-for-release-claims")
        self.assertFalse(report["gates"]["hard_suite_gate"]["pass"])

    def test_external_claim_ready_with_comparable_external_row(self) -> None:
        evaluator = ReleaseStatusEvaluator(policy_path="config/repro_policy.json")
        report = evaluator.evaluate(
            {
                "benchmark_progress": {
                    "ready": True,
                    "gaps": {"remaining_distance": 0.0},
                },
                "declared_baseline_comparison": {
                    "comparisons": [
                        {
                            "source_type": "external_reported",
                            "comparability": {"comparable": True},
                        }
                    ]
                },
            }
        )
        self.assertTrue(report["release_ready_internal"])
        self.assertTrue(report["external_claim_ready"])
        self.assertEqual(report["claim_scope"], "internal-and-declared-external-comparative")


if __name__ == "__main__":
    unittest.main()
