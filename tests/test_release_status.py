from __future__ import annotations

import json
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

    def _write_policy(
        self,
        *,
        min_external: int = 2,
        hard_suite_required: bool = True,
        moonshot_gate_enabled: bool = False,
    ) -> Path:
        path = self.temp_dir / "repro_policy.json"
        payload = {
            "release_gates": {
                "hard_suite_absolute_win_required": hard_suite_required,
                "moonshot_general_benchmarks_gate": moonshot_gate_enabled,
                "min_comparable_external_baselines_for_external_claim": min_external,
            }
        }
        path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        return path

    def test_internal_ready_without_external_claim(self) -> None:
        policy_path = self._write_policy(min_external=2)
        evaluator = ReleaseStatusEvaluator(policy_path=str(policy_path))
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
        self.assertEqual(report["gates"]["external_claim_gate"]["required_external_baselines"], 2)
        self.assertEqual(report["gates"]["external_claim_gate"]["external_claim_distance"], 2)
        self.assertEqual(report["gates"]["external_claim_gate"]["non_comparable_external_baselines"], 0)
        self.assertEqual(report["gates"]["external_claim_gate"]["blockers"], {})

    def test_not_ready_when_hard_suite_gate_fails(self) -> None:
        policy_path = self._write_policy(min_external=2)
        evaluator = ReleaseStatusEvaluator(policy_path=str(policy_path))
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
        policy_path = self._write_policy(min_external=1)
        evaluator = ReleaseStatusEvaluator(policy_path=str(policy_path))
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
        self.assertEqual(report["gates"]["external_claim_gate"]["external_claim_distance"], 0)

    def test_external_claim_blockers_and_distance_are_counted(self) -> None:
        policy_path = self._write_policy(min_external=2)
        evaluator = ReleaseStatusEvaluator(policy_path=str(policy_path))
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
                        },
                        {
                            "source_type": "external_reported",
                            "comparability": {
                                "comparable": False,
                                "reasons": ["suite_id_mismatch", "evidence_not_verified"],
                            },
                        },
                        {
                            "source_type": "external_reproduced",
                            "comparability": {"comparable": False},
                        },
                    ]
                },
            }
        )
        self.assertFalse(report["external_claim_ready"])
        self.assertEqual(report["gates"]["external_claim_gate"]["comparable_external_baselines"], 1)
        self.assertEqual(report["gates"]["external_claim_gate"]["required_external_baselines"], 2)
        self.assertEqual(report["gates"]["external_claim_gate"]["external_claim_distance"], 1)
        self.assertEqual(report["gates"]["external_claim_gate"]["non_comparable_external_baselines"], 2)
        self.assertEqual(report["gates"]["external_claim_gate"]["blockers"]["suite_id_mismatch"], 1)
        self.assertEqual(report["gates"]["external_claim_gate"]["blockers"]["evidence_not_verified"], 1)
        self.assertEqual(
            report["gates"]["external_claim_gate"]["blockers"]["unspecified-comparability-reason"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
