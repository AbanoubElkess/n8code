from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.external_claim_promotion import ExternalClaimPromotionService


class TestExternalClaimPromotionService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-claim-promotion-"))
        self.source_registry = self.temp_dir / "frontier_baselines.json"
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
        self.service = ExternalClaimPromotionService(policy_path=str(self.policy_path))
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

    def _build_valid_campaign(self) -> dict[str, object]:
        ingest_payload = self.temp_dir / "extra.json"
        ingest_payload.write_text(
            json.dumps(
                {
                    "baseline_id": "external-extra",
                    "label": "External Extra",
                    "source_type": "external_reported",
                    "source": "arxiv:2501.19393",
                    "source_date": "2026-02-17",
                    "verified": True,
                    "enabled": True,
                    "suite_id": "quantum_hard_suite_v2_adversarial",
                    "scoring_protocol": "src/agai/quantum_suite.py:263",
                    "evidence": {
                        "citation": "arxiv:2501.19393",
                        "artifact_hash": "sha256:extra",
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
        patch = self.temp_dir / "patch.json"
        patch.write_text(
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
        return {
            "ingest_payload_paths": [str(ingest_payload)],
            "baseline_runs": [
                {
                    "baseline_id": "external-placeholder",
                    "patch_overrides_path": str(patch),
                    "align_to_eval": True,
                    "replace_metrics": True,
                }
            ],
        }

    def test_preview_returns_hash_and_promotable_true_for_valid_campaign(self) -> None:
        campaign = self._build_valid_campaign()
        preview = self.service.preview(
            eval_report=self.eval_report,
            source_registry_path=str(self.source_registry),
            campaign_config=campaign,
            default_max_metric_delta=0.02,
        )
        self.assertEqual(preview["status"], "ok")
        self.assertTrue(preview["promotable"])
        self.assertEqual(preview["before"]["external_claim_distance"], 2)
        self.assertEqual(preview["projected_after"]["external_claim_distance"], 0)
        self.assertEqual(preview["projected_delta"]["total_claim_distance_reduction"], 2)
        self.assertGreater(preview["projected_delta"]["total_progress_ratio_gain"], 0.0)
        expected_hash = hashlib.sha256(self.source_registry.read_bytes()).hexdigest()
        self.assertEqual(preview["required_confirmation_hash"], expected_hash)

    def test_execute_requires_confirmation_hash(self) -> None:
        payload = self.service.execute(
            eval_report=self.eval_report,
            source_registry_path=str(self.source_registry),
            campaign_config={},
            default_max_metric_delta=0.02,
            confirmation_hash="",
        )
        self.assertEqual(payload["status"], "error")
        self.assertIn("confirmation hash is required", payload["reason"])

    def test_execute_applies_campaign_with_correct_hash(self) -> None:
        campaign = self._build_valid_campaign()
        confirmation_hash = hashlib.sha256(self.source_registry.read_bytes()).hexdigest()
        result = self.service.execute(
            eval_report=self.eval_report,
            source_registry_path=str(self.source_registry),
            campaign_config=campaign,
            default_max_metric_delta=0.02,
            confirmation_hash=confirmation_hash,
        )
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["source_registry_mutated"])
        self.assertEqual(result["before"]["external_claim_distance"], 2)
        self.assertEqual(result["after"]["external_claim_distance"], 0)
        self.assertEqual(result["delta"]["external_claim_distance_reduction"], 2)
        self.assertEqual(result["delta"]["total_claim_distance_reduction"], 2)
        self.assertGreater(result["delta"]["total_progress_ratio_gain"], 0.0)
        self.assertFalse(result["rollback_applied"])
        self.assertTrue(result["gate_evaluation"]["pass"])

    def test_execute_rolls_back_when_promotion_gate_fails(self) -> None:
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
                    },
                    "promotion_gates": {
                        "min_distance_reduction": 3,
                        "max_after_external_claim_distance": 0,
                        "require_external_claim_ready": False,
                    },
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        strict_service = ExternalClaimPromotionService(policy_path=str(self.policy_path))
        campaign = self._build_valid_campaign()
        before_bytes = self.source_registry.read_bytes()
        confirmation_hash = hashlib.sha256(before_bytes).hexdigest()
        result = strict_service.execute(
            eval_report=self.eval_report,
            source_registry_path=str(self.source_registry),
            campaign_config=campaign,
            default_max_metric_delta=0.02,
            confirmation_hash=confirmation_hash,
        )
        after_bytes = self.source_registry.read_bytes()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["execution_status"], "ok")
        self.assertTrue(result["rollback_applied"])
        self.assertEqual(result["rollback_reason"], "promotion gates failed")
        self.assertFalse(result["source_registry_mutated"])
        self.assertEqual(result["before"]["external_claim_distance"], 2)
        self.assertEqual(result["executed_after"]["external_claim_distance"], 0)
        self.assertEqual(result["after"]["external_claim_distance"], 2)
        self.assertFalse(result["gate_evaluation"]["pass"])
        self.assertIn("distance reduction", result["gate_evaluation"]["reason"])
        self.assertEqual(before_bytes, after_bytes)

    def test_execute_rolls_back_when_total_progress_ratio_gate_fails(self) -> None:
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
                    },
                    "promotion_gates": {
                        "min_distance_reduction": 1,
                        "max_after_external_claim_distance": 0,
                        "require_external_claim_ready": False,
                        "require_total_distance_non_increase": True,
                        "min_total_progress_ratio_gain": 0.80,
                    },
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        strict_service = ExternalClaimPromotionService(policy_path=str(self.policy_path))
        campaign = self._build_valid_campaign()
        before_bytes = self.source_registry.read_bytes()
        confirmation_hash = hashlib.sha256(before_bytes).hexdigest()
        result = strict_service.execute(
            eval_report=self.eval_report,
            source_registry_path=str(self.source_registry),
            campaign_config=campaign,
            default_max_metric_delta=0.02,
            confirmation_hash=confirmation_hash,
        )
        after_bytes = self.source_registry.read_bytes()
        self.assertEqual(result["status"], "error")
        self.assertTrue(result["rollback_applied"])
        self.assertFalse(result["source_registry_mutated"])
        self.assertFalse(result["gate_evaluation"]["pass"])
        self.assertIn("total progress ratio gain", result["gate_evaluation"]["reason"])
        self.assertEqual(before_bytes, after_bytes)


if __name__ == "__main__":
    unittest.main()
