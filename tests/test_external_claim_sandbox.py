from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.external_claim_sandbox import ExternalClaimSandboxPipeline


class TestExternalClaimSandboxPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-claim-sandbox-"))
        self.source_registry = self.temp_dir / "frontier_baselines.json"
        self.sandbox_registry = self.temp_dir / "sandbox_registry.json"
        self.source_registry.write_text(
            json.dumps(
                {
                    "registry_version": "test",
                    "baselines": [
                        {
                            "baseline_id": "external-placeholder",
                            "label": "External Placeholder",
                            "source_type": "external_reported",
                            "source": "pending-normalization",
                            "source_date": "unknown",
                            "verified": False,
                            "enabled": True,
                            "suite_id": "unknown-suite",
                            "scoring_protocol": "unknown-scoring",
                            "evidence": {
                                "citation": "",
                                "artifact_hash": "",
                                "retrieval_date": "",
                                "verification_method": "",
                                "replication_status": "pending",
                            },
                            "metrics": {},
                            "notes": "",
                        }
                    ],
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.eval_report = {
            "benchmark_progress": {
                "suite_id": "quantum_hard_suite_v2_adversarial",
                "observed": {
                    "quality": 0.90,
                    "aggregate_delta": 0.48,
                },
                "gaps": {"remaining_distance": 0.0},
                "ready": True,
            },
            "benchmark_provenance": {
                "scoring_reference": "src/agai/quantum_suite.py:263",
            },
            "claim_calibration": {
                "combined_average_reality_score": 0.95,
                "public_overclaim_rate": 0.01,
            },
        }
        self.pipeline = ExternalClaimSandboxPipeline(policy_path=str(self.temp_dir / "missing-policy.json"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pipeline_blocks_without_required_overrides(self) -> None:
        payload = self.pipeline.run(
            baseline_id="external-placeholder",
            eval_report=self.eval_report,
            source_registry_path=str(self.source_registry),
            sandbox_registry_path=str(self.sandbox_registry),
            patch_overrides=None,
            dry_run=False,
        )
        self.assertEqual(payload["status"], "blocked")
        self.assertFalse(payload["apply_executed"])
        self.assertTrue(payload["source_registry_unchanged"])
        self.assertGreater(len(payload["unresolved_fields"]), 0)
        self.assertEqual(payload["before"]["external_claim_distance"], 1)
        self.assertEqual(payload["after"]["external_claim_distance"], 1)

    def test_pipeline_reduces_distance_with_explicit_overrides(self) -> None:
        overrides = {
            "source": "arxiv:2501.12948",
            "source_date": "2026-02-17",
            "evidence": {
                "citation": "arxiv:2501.12948",
                "retrieval_date": "2026-02-17",
                "verification_method": "manual extraction",
            },
            "metrics": {
                "quality": 0.90,
                "aggregate_delta": 0.48,
            },
        }
        payload = self.pipeline.run(
            baseline_id="external-placeholder",
            eval_report=self.eval_report,
            source_registry_path=str(self.source_registry),
            sandbox_registry_path=str(self.sandbox_registry),
            patch_overrides=overrides,
            max_metric_delta=0.02,
            align_to_eval=True,
            replace_metrics=True,
            dry_run=False,
        )
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["apply_executed"])
        self.assertTrue(payload["source_registry_unchanged"])
        self.assertEqual(payload["unresolved_fields"], [])
        self.assertEqual(payload["normalization_result"]["status"], "ok")
        self.assertEqual(payload["before"]["external_claim_distance"], 1)
        self.assertEqual(payload["after"]["external_claim_distance"], 0)
        self.assertEqual(payload["delta"]["external_claim_distance_reduction"], 1)
        self.assertTrue(payload["after"]["external_claim_ready"])


if __name__ == "__main__":
    unittest.main()
