from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.external_claim_campaign_draft import ExternalClaimCampaignDraftService
from agai.runtime import AgenticRuntime


class TestExternalClaimCampaignDraftService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-claim-campaign-draft-"))
        self.service = ExternalClaimCampaignDraftService()
        self.claim_plan = {
            "row_plans": [
                {
                    "baseline_id": "external-a",
                    "actions": [
                        {"action_type": "refresh_evidence_payload"},
                        {"action_type": "attest_baseline"},
                    ],
                }
            ]
        }

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_reports_missing_patch_mapping_as_blocked(self) -> None:
        payload = self.service.build(claim_plan=self.claim_plan)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["summary"]["baseline_runs_ready"], 0)
        self.assertEqual(payload["summary"]["unresolved_dependencies"], 1)
        self.assertEqual(payload["campaign_config"]["baseline_runs"], [])

    def test_build_stages_valid_patch_and_ingest_payload(self) -> None:
        patch_path = self.temp_dir / "patch_external_a.json"
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
        ingest_path = self.temp_dir / "ingest_external_b.json"
        ingest_path.write_text(
            json.dumps({"baseline_id": "external-b"}, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        payload = self.service.build(
            claim_plan=self.claim_plan,
            patch_overrides_map={"external-a": str(patch_path)},
            ingest_payload_paths=[str(ingest_path)],
            default_max_metric_delta=0.03,
        )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["summary"]["baseline_runs_ready"], 1)
        self.assertEqual(payload["summary"]["ingest_payloads_ready"], 1)
        step = payload["campaign_config"]["baseline_runs"][0]
        self.assertEqual(step["baseline_id"], "external-a")
        self.assertEqual(step["patch_overrides_path"], str(patch_path))
        self.assertAlmostEqual(float(step["max_metric_delta"]), 0.03, places=6)

    def test_build_rejects_patch_with_unresolved_fields(self) -> None:
        patch_path = self.temp_dir / "patch_external_a_invalid.json"
        patch_path.write_text(
            json.dumps(
                {
                    "source": "",
                    "source_date": "2026-02-17",
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        payload = self.service.build(
            claim_plan=self.claim_plan,
            patch_overrides_map={"external-a": str(patch_path)},
        )
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["summary"]["baseline_runs_ready"], 0)
        self.assertEqual(payload["summary"]["unresolved_dependencies"], 1)
        self.assertIn("unresolved empty/null fields", payload["unresolved_dependencies"][0]["reason"])


class TestRuntimeExternalClaimCampaignDraft(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-runtime-claim-campaign-draft-"))
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
                        "ready": True,
                        "gaps": {"remaining_distance": 0.0},
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
        self.patch_path = self.temp_dir / "patch_external_placeholder.json"
        self.patch_path.write_text(
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
        self.patch_map_path = self.temp_dir / "patch_map.json"
        self.patch_map_path.write_text(
            json.dumps(
                {"external-placeholder": {"patch_overrides_path": str(self.patch_path)}},
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.ingest_payload_path = self.temp_dir / "ingest_external_extra.json"
        self.ingest_payload_path.write_text(
            json.dumps({"baseline_id": "external-extra"}, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        self.ingest_manifest_path = self.temp_dir / "ingest_manifest.json"
        self.ingest_manifest_path.write_text(
            json.dumps([str(self.ingest_payload_path)], ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_runtime_generates_campaign_draft_and_config_artifact(self) -> None:
        runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(self.temp_dir))
        payload = runtime.run_external_claim_campaign_draft(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            default_max_metric_delta=0.02,
            patch_map_path=str(self.patch_map_path),
            ingest_manifest_path=str(self.ingest_manifest_path),
        )
        self.assertEqual(payload["status"], "ok")
        self.assertIn("campaign_config", payload)
        self.assertIn("campaign_output_path", payload)
        self.assertTrue(Path(payload["campaign_output_path"]).exists())
        self.assertTrue((self.temp_dir / "external_claim_campaign_draft.json").exists())


if __name__ == "__main__":
    unittest.main()
