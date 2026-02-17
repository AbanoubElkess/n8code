from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.external_claim_campaign_evidence_schema import ExternalClaimCampaignEvidenceSchemaService
from agai.runtime import AgenticRuntime


class TestExternalClaimCampaignEvidenceSchemaService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-campaign-evidence-schema-"))
        self.patch_template = self.temp_dir / "patch_overrides_external_a.json"
        self.patch_template.write_text(
            json.dumps(
                {
                    "source": "",
                    "source_date": "",
                    "evidence": {
                        "citation": "",
                        "retrieval_date": "",
                        "verification_method": "",
                    },
                    "metrics": {
                        "quality": None,
                        "aggregate_delta": None,
                    },
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.scaffold_payload = {
            "status": "ok",
            "generated_files": [
                {
                    "baseline_id": "external-a",
                    "patch_overrides_path": str(self.patch_template),
                    "blocking_categories": ["source-metadata", "metrics-overlap"],
                }
            ],
        }
        self.eval_report = {
            "benchmark_progress": {"suite_id": "quantum_hard_suite_v2_adversarial"},
            "benchmark_provenance": {"scoring_reference": "src/agai/quantum_suite.py:263"},
        }
        self.service = ExternalClaimCampaignEvidenceSchemaService()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_generates_canonical_evidence_map_schema(self) -> None:
        output_path = self.temp_dir / "evidence_map.generated.json"
        payload = self.service.build(
            scaffold_payload=self.scaffold_payload,
            eval_report=self.eval_report,
            output_path=str(output_path),
            default_max_metric_delta=0.03,
        )
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(output_path.exists())
        content = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertIn("defaults", content)
        self.assertIn("baselines", content)
        self.assertIn("external-a", content["baselines"])
        entry = content["baselines"]["external-a"]
        self.assertTrue(entry["align_to_eval"])
        self.assertAlmostEqual(float(entry["max_metric_delta"]), 0.03, places=6)
        self.assertEqual(entry["metrics"]["quality"], "")
        self.assertEqual(entry["metrics"]["aggregate_delta"], "")
        self.assertIn("external-claim-campaign-autofill", payload["next_command_hint"])

    def test_build_empty_when_scaffold_has_no_generated_files(self) -> None:
        output_path = self.temp_dir / "evidence_map.empty.generated.json"
        payload = self.service.build(
            scaffold_payload={"status": "ok", "generated_files": []},
            eval_report=self.eval_report,
            output_path=str(output_path),
            default_max_metric_delta=0.02,
        )
        self.assertEqual(payload["status"], "empty")
        self.assertTrue(output_path.exists())
        content = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(content["baselines"], {})


class TestRuntimeExternalClaimCampaignEvidenceSchema(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-runtime-campaign-evidence-schema-"))
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

    def test_runtime_generates_evidence_schema_artifacts(self) -> None:
        runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(self.temp_dir))
        output_path = self.temp_dir / "campaign_evidence_map.generated.json"
        payload = runtime.run_external_claim_campaign_evidence_schema(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            default_max_metric_delta=0.02,
            scaffold_output_dir=str(self.temp_dir / "campaign_scaffold"),
            output_path=str(output_path),
        )
        self.assertEqual(payload["status"], "ok")
        self.assertIn("scaffold", payload)
        self.assertIn("schema", payload)
        self.assertTrue(output_path.exists())
        self.assertTrue((self.temp_dir / "external_claim_campaign_evidence_schema.json").exists())
        schema = payload["schema"]
        self.assertEqual(schema["status"], "ok")
        self.assertIn("next_command_hint", schema)


if __name__ == "__main__":
    unittest.main()
