from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.baseline_registry import DeclaredBaselineComparator
from agai.external_claim_replay import ExternalClaimReplayRunner
from agai.release_status import ReleaseStatusEvaluator


class TestExternalClaimReplayRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-claim-replay-"))
        self.policy_path = self.temp_dir / "repro_policy.json"
        self.registry_path = self.temp_dir / "frontier_baselines.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_policy(self) -> None:
        payload = {
            "release_gates": {
                "hard_suite_absolute_win_required": True,
                "moonshot_general_benchmarks_gate": False,
                "min_comparable_external_baselines_for_external_claim": 1,
                "require_claim_calibration_for_external_claim": True,
                "min_combined_average_reality_score_for_external_claim": 0.90,
                "max_public_overclaim_rate_for_external_claim": 0.05,
            }
        }
        self.policy_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def _write_registry(self) -> None:
        payload = {
            "registry_version": "test",
            "baselines": [
                {
                    "baseline_id": "external-unverified-replay",
                    "label": "External Unverified Replay Candidate",
                    "source_type": "external_reported",
                    "source": "paper-archive",
                    "source_date": "2026-02-17",
                    "verified": False,
                    "enabled": True,
                    "suite_id": "quantum_hard_suite_v2_adversarial",
                    "scoring_protocol": "src/agai/quantum_suite.py:263",
                    "evidence": {
                        "citation": "paper:example-123",
                        "artifact_hash": "sha256:example",
                        "retrieval_date": "2026-02-17",
                        "verification_method": "manual-check",
                        "replication_status": "pending",
                    },
                    "metrics": {
                        "quality": 0.89,
                        "aggregate_delta": 0.44,
                    },
                }
            ],
        }
        self.registry_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _eval_report(self) -> dict[str, object]:
        return {
            "benchmark_progress": {
                "ready": True,
                "suite_id": "quantum_hard_suite_v2_adversarial",
                "gaps": {"remaining_distance": 0.0},
                "observed": {
                    "quality": 0.90,
                    "aggregate_delta": 0.45,
                    "public_overclaim_rate": 0.01,
                },
            },
            "benchmark_provenance": {
                "scoring_reference": "src/agai/quantum_suite.py:263",
            },
            "claim_calibration": {
                "combined_average_reality_score": 0.95,
                "public_overclaim_rate": 0.01,
            },
        }

    def test_replay_converts_unverified_candidate_to_comparable_external(self) -> None:
        self._write_policy()
        self._write_registry()
        eval_report = self._eval_report()
        comparator = DeclaredBaselineComparator(registry_path=str(self.registry_path))
        eval_report["declared_baseline_comparison"] = comparator.compare(eval_report)
        release = ReleaseStatusEvaluator(policy_path=str(self.policy_path)).evaluate(eval_report)

        runner = ExternalClaimReplayRunner(policy_path=str(self.policy_path))
        payload = runner.run(
            eval_report=eval_report,
            release_status=release,
            registry_path=str(self.registry_path),
            max_metric_delta=0.02,
        )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["before"]["external_claim_distance"], 1)
        self.assertEqual(payload["after"]["external_claim_distance"], 0)
        self.assertTrue(payload["after"]["external_claim_ready"])
        self.assertEqual(payload["delta"]["external_claim_distance_reduction"], 1)
        self.assertEqual(payload["delta"]["comparable_external_baselines_increase"], 1)
        self.assertEqual(payload["replay_summary"]["attempted_rows"], 1)
        self.assertEqual(payload["replay_summary"]["passed_rows"], 1)
        self.assertEqual(payload["replay_summary"]["failed_rows"], 0)
        self.assertEqual(payload["replay_summary"]["skipped_manual_rows"], 0)

    def test_replay_dry_run_does_not_mutate_distance(self) -> None:
        self._write_policy()
        self._write_registry()
        eval_report = self._eval_report()
        comparator = DeclaredBaselineComparator(registry_path=str(self.registry_path))
        eval_report["declared_baseline_comparison"] = comparator.compare(eval_report)
        release = ReleaseStatusEvaluator(policy_path=str(self.policy_path)).evaluate(eval_report)

        runner = ExternalClaimReplayRunner(policy_path=str(self.policy_path))
        payload = runner.run(
            eval_report=eval_report,
            release_status=release,
            registry_path=str(self.registry_path),
            max_metric_delta=0.02,
            dry_run=True,
        )
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["before"]["external_claim_distance"], 1)
        self.assertEqual(payload["after"]["external_claim_distance"], 1)
        self.assertEqual(payload["delta"]["external_claim_distance_reduction"], 0)
        self.assertEqual(payload["replay_summary"]["candidate_rows"], 1)
        self.assertEqual(payload["replay_summary"]["attempted_rows"], 0)
        self.assertEqual(payload["replay_summary"]["passed_rows"], 0)
        self.assertEqual(payload["replay_summary"]["failed_rows"], 0)
        self.assertEqual(payload["replay_summary"]["skipped_manual_rows"], 0)


if __name__ == "__main__":
    unittest.main()
