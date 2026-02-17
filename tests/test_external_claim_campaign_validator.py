from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.external_claim_campaign_validator import ExternalClaimCampaignValidatorService
from agai.runtime import AgenticRuntime


class TestExternalClaimCampaignValidatorService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-campaign-validator-"))
        self.registry_path = self.temp_dir / "frontier_baselines.json"
        self.registry_path.write_text(
            json.dumps(
                {"registry_version": "test", "baselines": []},
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
            },
            "benchmark_provenance": {
                "scoring_reference": "src/agai/quantum_suite.py:263",
            },
        }
        self.claim_plan = {
            "row_plans": [
                {
                    "baseline_id": "external-a",
                    "actions": [
                        {"action_type": "refresh_evidence_payload"},
                        {"action_type": "normalize_metadata_dates"},
                        {"action_type": "normalize_harness_alignment"},
                        {"action_type": "add_overlapping_metrics"},
                        {"action_type": "attest_baseline"},
                    ],
                }
            ]
        }
        self.validator = ExternalClaimCampaignValidatorService()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_reports_missing_patch_mapping(self) -> None:
        payload = self.validator.validate(
            claim_plan=self.claim_plan,
            patch_overrides_map={},
            ingest_payload_paths=[],
            eval_report=self.eval_report,
            registry_path=str(self.registry_path),
        )
        self.assertEqual(payload["status"], "error")
        self.assertGreater(payload["summary"]["issues"], 0)
        self.assertEqual(payload["baseline_checks"][0]["status"], "error")

    def test_validate_reports_placeholder_patch_fields(self) -> None:
        patch_path = self.temp_dir / "patch_invalid.json"
        patch_path.write_text(
            json.dumps(
                {
                    "source": "pending-source",
                    "source_date": "2026/02/17",
                    "evidence": {
                        "citation": "",
                        "retrieval_date": "not-a-date",
                        "verification_method": "",
                    },
                    "metrics": {"quality": "bad"},
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        payload = self.validator.validate(
            claim_plan=self.claim_plan,
            patch_overrides_map={
                "external-a": {
                    "patch_overrides_path": str(patch_path),
                    "align_to_eval": False,
                }
            },
            ingest_payload_paths=[],
            eval_report=self.eval_report,
            registry_path=str(self.registry_path),
        )
        self.assertEqual(payload["status"], "error")
        self.assertGreater(payload["summary"]["issues"], 0)
        issue_codes = [issue["code"] for issue in payload["issues"]]
        self.assertIn("invalid_source_date", issue_codes)
        self.assertIn("non_numeric_metric", issue_codes)

    def test_validate_passes_for_filled_patch_and_ingest_payload(self) -> None:
        patch_path = self.temp_dir / "patch_valid.json"
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
        ingest_path = self.temp_dir / "ingest_valid.json"
        ingest_path.write_text(
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
        payload = self.validator.validate(
            claim_plan=self.claim_plan,
            patch_overrides_map={"external-a": str(patch_path)},
            ingest_payload_paths=[str(ingest_path)],
            eval_report=self.eval_report,
            registry_path=str(self.registry_path),
        )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["summary"]["issues"], 0)
        self.assertEqual(payload["baseline_checks"][0]["status"], "ok")
        self.assertEqual(payload["ingest_checks"][0]["status"], "ok")


class TestRuntimeExternalClaimCampaignValidate(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-runtime-campaign-validate-"))
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
                        "observed": {"quality": 0.90, "aggregate_delta": 0.48},
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

    def test_runtime_validate_reports_issues_for_scaffold_templates(self) -> None:
        runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(self.temp_dir))
        scaffold = runtime.run_external_claim_campaign_scaffold(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            output_dir=str(self.temp_dir / "campaign_scaffold"),
        )
        self.assertEqual(scaffold["status"], "ok")
        payload = runtime.run_external_claim_campaign_validate(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            patch_map_path=str(scaffold["patch_map_path"]),
            ingest_manifest_path=str(scaffold["ingest_manifest_path"]),
        )
        self.assertEqual(payload["status"], "error")
        self.assertGreater(payload["summary"]["issues"], 0)
        self.assertTrue((self.temp_dir / "external_claim_campaign_validate.json").exists())


if __name__ == "__main__":
    unittest.main()
