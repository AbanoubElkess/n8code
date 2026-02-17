from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.external_claim_campaign_scaffold import ExternalClaimCampaignScaffoldService
from agai.runtime import AgenticRuntime


class TestExternalClaimCampaignScaffoldService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-claim-campaign-scaffold-"))
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
                    "baseline_id": "external-placeholder",
                    "actions": [
                        {"action_type": "refresh_evidence_payload"},
                        {"action_type": "normalize_harness_alignment"},
                        {"action_type": "attest_baseline"},
                    ],
                }
            ]
        }
        self.service = ExternalClaimCampaignScaffoldService()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_generates_scaffold_files(self) -> None:
        output_dir = self.temp_dir / "campaign_scaffold"
        payload = self.service.build(
            claim_plan=self.claim_plan,
            eval_report=self.eval_report,
            registry_path=str(self.registry_path),
            output_dir=str(output_dir),
            default_max_metric_delta=0.03,
        )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["summary"]["targeted_rows"], 1)
        self.assertEqual(payload["summary"]["generated_patch_files"], 1)
        self.assertTrue(Path(payload["patch_map_path"]).exists())
        self.assertTrue(Path(payload["ingest_manifest_path"]).exists())

        patch_map = json.loads(Path(payload["patch_map_path"]).read_text(encoding="utf-8"))
        self.assertIn("external-placeholder", patch_map)
        self.assertAlmostEqual(
            float(patch_map["external-placeholder"]["max_metric_delta"]),
            0.03,
            places=6,
        )
        patch_path = Path(patch_map["external-placeholder"]["patch_overrides_path"])
        self.assertTrue(patch_path.exists())
        self.assertTrue(len(patch_path.read_text(encoding="utf-8").strip()) > 2)

        generated_file = payload["generated_files"][0]
        self.assertEqual(generated_file["baseline_id"], "external-placeholder")
        self.assertTrue(generated_file["requires_manual_fill"])
        self.assertGreater(len(generated_file["unresolved_fields"]), 0)

    def test_build_returns_empty_when_no_manual_patch_actions(self) -> None:
        claim_plan = {
            "row_plans": [
                {
                    "baseline_id": "external-placeholder",
                    "actions": [{"action_type": "attest_baseline"}],
                }
            ]
        }
        output_dir = self.temp_dir / "campaign_scaffold_empty"
        payload = self.service.build(
            claim_plan=claim_plan,
            eval_report=self.eval_report,
            registry_path=str(self.registry_path),
            output_dir=str(output_dir),
            default_max_metric_delta=0.02,
        )
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["summary"]["targeted_rows"], 0)
        self.assertEqual(payload["summary"]["generated_patch_files"], 0)
        self.assertTrue(Path(payload["patch_map_path"]).exists())


class TestRuntimeExternalClaimCampaignScaffold(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-runtime-campaign-scaffold-"))
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

    def test_runtime_scaffold_then_draft_stays_truthful_when_templates_unfilled(self) -> None:
        runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(self.temp_dir))
        scaffold = runtime.run_external_claim_campaign_scaffold(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            default_max_metric_delta=0.02,
            output_dir=str(self.temp_dir / "campaign_scaffold"),
        )
        self.assertEqual(scaffold["status"], "ok")
        self.assertTrue(Path(scaffold["patch_map_path"]).exists())
        self.assertTrue(Path(scaffold["ingest_manifest_path"]).exists())
        self.assertTrue((self.temp_dir / "external_claim_campaign_scaffold.json").exists())

        draft = runtime.run_external_claim_campaign_draft(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            default_max_metric_delta=0.02,
            patch_map_path=str(scaffold["patch_map_path"]),
            ingest_manifest_path=str(scaffold["ingest_manifest_path"]),
        )
        self.assertEqual(draft["status"], "blocked")
        self.assertEqual(draft["summary"]["baseline_runs_ready"], 0)
        self.assertEqual(draft["summary"]["unresolved_dependencies"], 1)
        self.assertIn("unresolved empty/null fields", draft["unresolved_dependencies"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
