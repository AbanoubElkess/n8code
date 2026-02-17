from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.baseline_patch_template import ExternalBaselinePatchTemplateService


class TestExternalBaselinePatchTemplateService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-baseline-patch-template-"))
        self.registry_path = self.temp_dir / "frontier_baselines.json"
        self.service = ExternalBaselinePatchTemplateService(registry_path=str(self.registry_path))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_template_includes_required_fields_for_placeholder_row(self) -> None:
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
        eval_report = {
            "benchmark_progress": {
                "suite_id": "quantum_hard_suite_v2_adversarial",
                "observed": {
                    "quality": 0.91,
                    "aggregate_delta": 0.48,
                    "public_overclaim_rate": 0.0,
                },
            },
            "benchmark_provenance": {
                "scoring_reference": "src/agai/quantum_suite.py:263",
            },
        }
        template = self.service.build_template(
            baseline_id="external-placeholder",
            eval_report=eval_report,
        )
        self.assertEqual(template["status"], "ok")
        self.assertFalse(template["comparable"])
        self.assertIn("suite mismatch", template["comparability_reasons"])
        self.assertIn("scoring protocol mismatch", template["comparability_reasons"])
        patch = template["patch_template"]
        self.assertIn("source", patch)
        self.assertIn("source_date", patch)
        self.assertIn("evidence", patch)
        self.assertIn("citation", patch["evidence"])
        self.assertIn("retrieval_date", patch["evidence"])
        self.assertIn("verification_method", patch["evidence"])
        self.assertEqual(patch["suite_id"], "quantum_hard_suite_v2_adversarial")
        self.assertEqual(patch["scoring_protocol"], "src/agai/quantum_suite.py:263")
        self.assertIn("metrics", patch)
        self.assertIn("quality", patch["metrics"])
        self.assertIn("aggregate_delta", patch["metrics"])

    def test_template_empty_for_comparable_row(self) -> None:
        self.registry_path.write_text(
            json.dumps(
                {
                    "registry_version": "test",
                    "baselines": [
                        {
                            "baseline_id": "external-comparable",
                            "label": "External Comparable",
                            "source_type": "external_reported",
                            "source": "arxiv:2501.12948",
                            "source_date": "2026-02-17",
                            "verified": True,
                            "enabled": True,
                            "suite_id": "quantum_hard_suite_v2_adversarial",
                            "scoring_protocol": "src/agai/quantum_suite.py:263",
                            "evidence": {
                                "citation": "arxiv:2501.12948",
                                "artifact_hash": "sha256:external-comparable",
                                "retrieval_date": "2026-02-17",
                                "verification_method": "manual extraction",
                                "replication_status": "replicated-internal-harness",
                            },
                            "metrics": {
                                "quality": 0.90,
                                "aggregate_delta": 0.45,
                            },
                        }
                    ],
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        eval_report = {
            "benchmark_progress": {
                "suite_id": "quantum_hard_suite_v2_adversarial",
                "observed": {
                    "quality": 0.91,
                    "aggregate_delta": 0.48,
                },
            },
            "benchmark_provenance": {
                "scoring_reference": "src/agai/quantum_suite.py:263",
            },
        }
        template = self.service.build_template(
            baseline_id="external-comparable",
            eval_report=eval_report,
        )
        self.assertEqual(template["status"], "ok")
        self.assertTrue(template["comparable"])
        self.assertEqual(template["patch_template"], {})
        self.assertEqual(template["blocking_categories"], [])

    def test_template_errors_when_baseline_missing(self) -> None:
        self.registry_path.write_text(json.dumps({"registry_version": "test", "baselines": []}), encoding="utf-8")
        template = self.service.build_template(
            baseline_id="missing-baseline",
            eval_report={},
        )
        self.assertEqual(template["status"], "error")
        self.assertIn("baseline not found", template["reason"])


if __name__ == "__main__":
    unittest.main()
