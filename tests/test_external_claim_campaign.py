from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.external_claim_campaign import ExternalClaimSandboxCampaignRunner


class TestExternalClaimSandboxCampaignRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-claim-campaign-"))
        self.source_registry = self.temp_dir / "frontier_baselines.json"
        self.sandbox_registry = self.temp_dir / "sandbox_registry.json"
        self.policy_path = self.temp_dir / "repro_policy.json"
        self.policy_path.write_text(
            json.dumps(
                {
                    "release_gates": {
                        "hard_suite_absolute_win_required": True,
                        "moonshot_general_benchmarks_gate": False,
                        "min_comparable_external_baselines_for_external_claim": 2,
                        "require_claim_calibration_for_external_claim": True,
                        "min_combined_average_reality_score_for_external_claim": 0.90,
                        "max_public_overclaim_rate_for_external_claim": 0.05,
                    }
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.runner = ExternalClaimSandboxCampaignRunner(policy_path=str(self.policy_path))
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
                        }
                    ],
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_campaign_reports_partial_when_unresolved_fields_remain(self) -> None:
        campaign_config = {
            "baseline_runs": [
                {
                    "baseline_id": "external-placeholder",
                    "dry_run": False,
                }
            ]
        }
        payload = self.runner.run(
            eval_report=self.eval_report,
            source_registry_path=str(self.source_registry),
            sandbox_registry_path=str(self.sandbox_registry),
            campaign_config=campaign_config,
            default_max_metric_delta=0.02,
        )
        self.assertEqual(payload["status"], "partial")
        self.assertTrue(payload["source_registry_unchanged"])
        self.assertEqual(payload["before"]["external_claim_distance"], 2)
        self.assertEqual(payload["after"]["external_claim_distance"], 2)
        self.assertEqual(payload["delta"]["external_claim_distance_reduction"], 0)
        self.assertIn("total_claim_distance", payload["before"])
        self.assertIn("total_progress_ratio", payload["before"])
        self.assertIn("total_claim_distance_reduction", payload["delta"])
        self.assertIn("total_progress_ratio_gain", payload["delta"])
        step = payload["baseline_steps"]["results"][0]
        self.assertEqual(step["status"], "blocked")
        self.assertGreater(len(step["unresolved_fields"]), 0)

    def test_campaign_can_reach_zero_distance_with_ingest_and_patch(self) -> None:
        ingest_payload_path = self.temp_dir / "external_ingest.json"
        ingest_payload_path.write_text(
            json.dumps(
                {
                    "baseline_id": "external-extra",
                    "label": "External Extra Comparable",
                    "source_type": "external_reported",
                    "source": "arxiv:2501.19393",
                    "source_date": "2026-02-17",
                    "verified": True,
                    "enabled": True,
                    "suite_id": "quantum_hard_suite_v2_adversarial",
                    "scoring_protocol": "src/agai/quantum_suite.py:263",
                    "evidence": {
                        "citation": "arxiv:2501.19393",
                        "artifact_hash": "sha256:external-extra",
                        "retrieval_date": "2026-02-17",
                        "verification_method": "manual extraction",
                        "replication_status": "replicated-internal-harness",
                    },
                    "metrics": {
                        "quality": 0.90,
                        "aggregate_delta": 0.48,
                    },
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        overrides_path = self.temp_dir / "placeholder_patch.json"
        overrides_path.write_text(
            json.dumps(
                {
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
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        campaign_config = {
            "ingest_payload_paths": [str(ingest_payload_path)],
            "baseline_runs": [
                {
                    "baseline_id": "external-placeholder",
                    "patch_overrides_path": str(overrides_path),
                    "align_to_eval": True,
                    "replace_metrics": True,
                    "dry_run": False,
                }
            ],
        }
        payload = self.runner.run(
            eval_report=self.eval_report,
            source_registry_path=str(self.source_registry),
            sandbox_registry_path=str(self.sandbox_registry),
            campaign_config=campaign_config,
            default_max_metric_delta=0.02,
        )
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["source_registry_unchanged"])
        self.assertEqual(payload["before"]["external_claim_distance"], 2)
        self.assertEqual(payload["after"]["external_claim_distance"], 0)
        self.assertEqual(payload["delta"]["external_claim_distance_reduction"], 2)
        self.assertEqual(payload["delta"]["total_claim_distance_reduction"], 2)
        step = payload["baseline_steps"]["results"][0]
        self.assertEqual(step["status"], "ok")
        self.assertEqual(step["delta"]["external_claim_distance_reduction"], 1)
        self.assertEqual(step["delta"]["total_claim_distance_reduction"], 1)
        self.assertEqual(payload["ingest_stage"]["results"][0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
