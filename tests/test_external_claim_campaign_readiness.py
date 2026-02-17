from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.external_claim_campaign_readiness import ExternalClaimCampaignReadinessService
from agai.runtime import AgenticRuntime


class TestExternalClaimCampaignReadinessService(unittest.TestCase):
    def test_blocked_when_draft_has_unresolved_dependencies(self) -> None:
        service = ExternalClaimCampaignReadinessService()
        payload = service.evaluate(
            draft_payload={
                "status": "blocked",
                "summary": {
                    "unresolved_dependencies": 1,
                },
                "campaign_config": {
                    "ingest_payload_paths": [],
                    "baseline_runs": [],
                },
            },
            preview_payload=None,
        )
        self.assertEqual(payload["status"], "blocked")
        self.assertFalse(payload["ready_for_preview"])
        self.assertFalse(payload["ready_for_execute"])
        self.assertFalse(payload["preview_gate"]["executed"])

    def test_ready_for_preview_without_preview_payload(self) -> None:
        service = ExternalClaimCampaignReadinessService()
        payload = service.evaluate(
            draft_payload={
                "status": "ok",
                "summary": {
                    "unresolved_dependencies": 0,
                },
                "campaign_config": {
                    "ingest_payload_paths": [],
                    "baseline_runs": [{"baseline_id": "external-a"}],
                },
            },
            preview_payload=None,
        )
        self.assertEqual(payload["status"], "ready-for-preview")
        self.assertTrue(payload["ready_for_preview"])
        self.assertFalse(payload["ready_for_execute"])
        self.assertFalse(payload["preview_gate"]["executed"])

    def test_ready_for_execute_when_preview_is_promotable(self) -> None:
        service = ExternalClaimCampaignReadinessService()
        payload = service.evaluate(
            draft_payload={
                "status": "ok",
                "summary": {
                    "unresolved_dependencies": 0,
                },
                "campaign_config": {
                    "ingest_payload_paths": [],
                    "baseline_runs": [{"baseline_id": "external-a"}],
                },
            },
            preview_payload={
                "status": "ok",
                "promotable": True,
                "gate_evaluation": {
                    "pass": True,
                    "reasons": [],
                },
            },
        )
        self.assertEqual(payload["status"], "ready-for-execute")
        self.assertTrue(payload["ready_for_preview"])
        self.assertTrue(payload["ready_for_execute"])
        self.assertTrue(payload["preview_gate"]["executed"])
        self.assertTrue(payload["preview_gate"]["promotable"])


class TestRuntimeExternalClaimCampaignReadiness(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-runtime-campaign-readiness-"))
        self.registry_path = self.temp_dir / "frontier_baselines.json"
        self.registry_path.write_text(
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
        self.eval_path = self.temp_dir / "eval.json"
        self.eval_path.write_text(
            json.dumps(
                {
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
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_readiness_blocked_for_unfilled_scaffold_templates(self) -> None:
        runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(self.temp_dir))
        scaffold = runtime.run_external_claim_campaign_scaffold(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            default_max_metric_delta=0.02,
            output_dir=str(self.temp_dir / "campaign_scaffold"),
        )
        self.assertEqual(scaffold["status"], "ok")
        payload = runtime.run_external_claim_campaign_readiness(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            default_max_metric_delta=0.02,
            patch_map_path=str(scaffold["patch_map_path"]),
            ingest_manifest_path=str(scaffold["ingest_manifest_path"]),
        )
        self.assertEqual(payload["status"], "blocked")
        self.assertFalse(payload["ready_for_preview"])
        self.assertFalse(payload["ready_for_execute"])
        self.assertEqual(payload["preview"]["status"], "not-executed")
        self.assertTrue((self.temp_dir / "external_claim_campaign_readiness.json").exists())

    def test_readiness_ready_for_execute_with_filled_inputs(self) -> None:
        runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(self.temp_dir))
        patch_path = self.temp_dir / "patch_external_placeholder.json"
        patch_path.write_text(
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
        patch_map_path = self.temp_dir / "patch_map.json"
        patch_map_path.write_text(
            json.dumps(
                {
                    "external-placeholder": {
                        "patch_overrides_path": str(patch_path),
                        "align_to_eval": True,
                        "replace_metrics": True,
                        "max_metric_delta": 0.02,
                    }
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        ingest_payload = self.temp_dir / "ingest_external_extra.json"
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
        ingest_manifest_path = self.temp_dir / "ingest_manifest.json"
        ingest_manifest_path.write_text(
            json.dumps([str(ingest_payload)], ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        payload = runtime.run_external_claim_campaign_readiness(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            default_max_metric_delta=0.02,
            patch_map_path=str(patch_map_path),
            ingest_manifest_path=str(ingest_manifest_path),
        )
        self.assertEqual(payload["status"], "ready-for-execute")
        self.assertTrue(payload["ready_for_preview"])
        self.assertTrue(payload["ready_for_execute"])
        self.assertEqual(payload["draft"]["status"], "ok")
        self.assertEqual(payload["preview"]["status"], "ok")
        self.assertTrue(payload["preview"]["promotable"])
        self.assertTrue((self.temp_dir / "external_claim_campaign_readiness.json").exists())
        self.assertTrue(Path(payload["campaign_output_path"]).exists())


if __name__ == "__main__":
    unittest.main()
