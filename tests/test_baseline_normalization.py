from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.baseline_normalization import ExternalBaselineNormalizationService


class TestExternalBaselineNormalizationService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-baseline-normalize-"))
        self.registry_path = self.temp_dir / "frontier_baselines.json"
        self.service = ExternalBaselineNormalizationService(registry_path=str(self.registry_path))
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
                                "citation": "pending citation",
                                "artifact_hash": "sha256:placeholder",
                                "retrieval_date": "unknown",
                                "verification_method": "pending",
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

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalize_updates_placeholder_row_with_explicit_patch(self) -> None:
        eval_report = {
            "benchmark_progress": {"suite_id": "quantum_hard_suite_v2_adversarial"},
            "benchmark_provenance": {"scoring_reference": "src/agai/quantum_suite.py:263"},
        }
        patch = {
            "source": "arxiv:2501.12948",
            "source_date": "2026-02-17",
            "evidence": {
                "citation": "arxiv:2501.12948",
                "retrieval_date": "2026-02-17",
                "verification_method": "manual extraction",
            },
            "metrics": {
                "quality": 0.88,
                "aggregate_delta": 0.41,
            },
        }
        result = self.service.normalize_payload(
            baseline_id="external-placeholder",
            patch=patch,
            eval_report=eval_report,
            align_to_eval=True,
            replace_metrics=True,
        )
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["normalize_applied"])
        self.assertTrue(result["align_to_eval"])
        self.assertIn("source", result["changed_fields"])
        self.assertIn("source_date", result["changed_fields"])
        self.assertIn("suite_id", result["changed_fields"])
        self.assertIn("scoring_protocol", result["changed_fields"])
        self.assertIn("metrics.quality", result["changed_fields"])
        self.assertIn("metrics.aggregate_delta", result["changed_fields"])
        self.assertFalse(result["verified_effective"])

        stored = json.loads(self.registry_path.read_text(encoding="utf-8"))
        row = stored["baselines"][0]
        self.assertEqual(row["source"], "arxiv:2501.12948")
        self.assertEqual(row["source_date"], "2026-02-17")
        self.assertEqual(row["suite_id"], "quantum_hard_suite_v2_adversarial")
        self.assertEqual(row["scoring_protocol"], "src/agai/quantum_suite.py:263")
        self.assertIn("quality", row["metrics"])

    def test_normalize_rejects_invalid_patch_content(self) -> None:
        patch = {
            "source": "pending-normalization",
            "source_date": "unknown",
        }
        result = self.service.normalize_payload(
            baseline_id="external-placeholder",
            patch=patch,
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "validation failed")
        self.assertIn("source must not be placeholder or unknown", result["errors"])
        self.assertIn("source_date must be ISO-8601 date (YYYY-MM-DD)", result["errors"])

    def test_normalize_errors_when_baseline_missing(self) -> None:
        result = self.service.normalize_payload(
            baseline_id="does-not-exist",
            patch={},
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("baseline not found", result["reason"])


if __name__ == "__main__":
    unittest.main()
