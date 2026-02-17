from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.external_claim_campaign_autofill import ExternalClaimCampaignAutofillService
from agai.runtime import AgenticRuntime


class TestExternalClaimCampaignAutofillService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-campaign-autofill-"))
        self.scaffold_dir = self.temp_dir / "scaffold"
        self.scaffold_dir.mkdir(parents=True, exist_ok=True)
        self.patch_template = self.scaffold_dir / "patch_overrides_external_a.json"
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
                }
            ],
        }
        self.eval_report = {
            "benchmark_progress": {
                "suite_id": "quantum_hard_suite_v2_adversarial",
                "observed": {"quality": 0.90, "aggregate_delta": 0.48},
            },
            "benchmark_provenance": {
                "scoring_reference": "src/agai/quantum_suite.py:263",
            },
        }
        self.service = ExternalClaimCampaignAutofillService()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_autofill_blocked_when_required_fields_missing(self) -> None:
        evidence_map = {
            "baselines": {
                "external-a": {
                    "source": "arxiv:2501.12948",
                }
            }
        }
        payload = self.service.build(
            scaffold_payload=self.scaffold_payload,
            evidence_map=evidence_map,
            eval_report=self.eval_report,
            output_dir=str(self.temp_dir / "autofill"),
        )
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["summary"]["baselines_total"], 1)
        self.assertEqual(payload["summary"]["baselines_unresolved"], 1)
        self.assertTrue(Path(payload["patch_map_path"]).exists())
        self.assertTrue(Path(payload["ingest_manifest_path"]).exists())

    def test_autofill_ok_when_evidence_is_complete(self) -> None:
        evidence_map = {
            "defaults": {
                "align_to_eval": True,
                "replace_metrics": True,
                "max_metric_delta": 0.02,
            },
            "baselines": {
                "external-a": {
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
            },
        }
        payload = self.service.build(
            scaffold_payload=self.scaffold_payload,
            evidence_map=evidence_map,
            eval_report=self.eval_report,
            output_dir=str(self.temp_dir / "autofill"),
        )
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["summary"]["baselines_unresolved"], 0)
        self.assertTrue(Path(payload["patch_map_path"]).exists())
        self.assertTrue(Path(payload["ingest_manifest_path"]).exists())
        patch_map = json.loads(Path(payload["patch_map_path"]).read_text(encoding="utf-8"))
        self.assertIn("external-a", patch_map)
        filled_path = Path(patch_map["external-a"]["patch_overrides_path"])
        self.assertTrue(filled_path.exists())
        filled_payload = json.loads(filled_path.read_text(encoding="utf-8"))
        self.assertEqual(filled_payload["suite_id"], "quantum_hard_suite_v2_adversarial")
        self.assertEqual(filled_payload["scoring_protocol"], "src/agai/quantum_suite.py:263")


class TestRuntimeExternalClaimCampaignAutofill(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-runtime-campaign-autofill-"))
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

    def test_runtime_autofill_blocked_with_incomplete_evidence_map(self) -> None:
        runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(self.temp_dir))
        evidence_map = self.temp_dir / "evidence_map_incomplete.json"
        evidence_map.write_text(
            json.dumps(
                {
                    "baselines": {
                        "external-placeholder": {
                            "source": "arxiv:2501.12948",
                        }
                    }
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        payload = runtime.run_external_claim_campaign_autofill(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            evidence_map_path=str(evidence_map),
            default_max_metric_delta=0.02,
            scaffold_output_dir=str(self.temp_dir / "campaign_scaffold"),
            autofill_output_dir=str(self.temp_dir / "campaign_autofill"),
        )
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["readiness"]["status"], "blocked")
        self.assertEqual(payload["readiness"]["input_validation"]["status"], "error")
        self.assertTrue((self.temp_dir / "external_claim_campaign_autofill.json").exists())

    def test_runtime_autofill_ready_for_execute_with_complete_evidence_map(self) -> None:
        runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(self.temp_dir))
        ingest_payload = self.temp_dir / "external_extra_ingest.json"
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
        evidence_map = self.temp_dir / "evidence_map_complete.json"
        evidence_map.write_text(
            json.dumps(
                {
                    "defaults": {
                        "align_to_eval": True,
                        "replace_metrics": True,
                        "max_metric_delta": 0.02,
                    },
                    "baselines": {
                        "external-placeholder": {
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
                    },
                    "ingest_payload_paths": [str(ingest_payload)],
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        payload = runtime.run_external_claim_campaign_autofill(
            registry_path=str(self.registry_path),
            eval_path=str(self.eval_path),
            evidence_map_path=str(evidence_map),
            default_max_metric_delta=0.02,
            scaffold_output_dir=str(self.temp_dir / "campaign_scaffold"),
            autofill_output_dir=str(self.temp_dir / "campaign_autofill"),
        )
        self.assertEqual(payload["status"], "ready-for-execute")
        self.assertEqual(payload["autofill"]["status"], "ok")
        self.assertEqual(payload["readiness"]["status"], "ready-for-execute")
        self.assertEqual(payload["readiness"]["input_validation"]["status"], "ok")
        self.assertTrue((self.temp_dir / "external_claim_campaign_autofill.json").exists())


if __name__ == "__main__":
    unittest.main()
