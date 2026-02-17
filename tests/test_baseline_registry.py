from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.baseline_registry import DeclaredBaselineComparator


class TestDeclaredBaselineComparator(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-baseline-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_compare_with_comparable_and_non_comparable_rows(self) -> None:
        registry_path = self.temp_dir / "frontier_baselines.json"
        registry = {
            "registry_version": "test-v1",
            "baselines": [
                {
                    "baseline_id": "ok-baseline",
                    "label": "Comparable baseline",
                    "source_type": "internal_reference",
                    "source": "test",
                    "source_date": "2026-02-17",
                    "verified": True,
                    "enabled": True,
                    "suite_id": "quantum_hard_suite_v2_adversarial",
                    "scoring_protocol": "src/agai/quantum_suite.py:263",
                    "evidence": {
                        "citation": "test citation",
                        "artifact_hash": "sha256:test",
                        "retrieval_date": "2026-02-17",
                        "verification_method": "test replay",
                        "replication_status": "replicated-internal-harness",
                    },
                    "metrics": {
                        "quality": 0.80,
                        "aggregate_delta": 0.20,
                        "holdout_quality": 0.75,
                        "adversarial_quality": 0.70,
                        "public_overclaim_rate": 0.10,
                    },
                },
                {
                    "baseline_id": "bad-baseline",
                    "label": "Non-comparable baseline",
                    "source_type": "external_reported",
                    "source": "test",
                    "source_date": "unknown",
                    "verified": False,
                    "enabled": True,
                    "suite_id": "other-suite",
                    "scoring_protocol": "other-scoring",
                    "evidence": {
                        "citation": "",
                        "artifact_hash": "",
                        "retrieval_date": "",
                        "verification_method": "",
                        "replication_status": "pending",
                    },
                    "metrics": {},
                },
            ],
        }
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        eval_report = {
            "benchmark_provenance": {"scoring_reference": "src/agai/quantum_suite.py:263"},
            "benchmark_progress": {
                "suite_id": "quantum_hard_suite_v2_adversarial",
                "observed": {
                    "quality": 0.90,
                    "aggregate_delta": 0.30,
                    "holdout_quality": 0.88,
                    "adversarial_quality": 0.86,
                    "public_overclaim_rate": 0.01,
                },
            },
        }

        report = DeclaredBaselineComparator(registry_path=str(registry_path)).compare(eval_report)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["summary"]["total_baselines"], 2)
        self.assertEqual(report["summary"]["comparable_baselines"], 1)
        self.assertEqual(report["summary"]["comparable_internal_baselines"], 1)
        self.assertEqual(report["summary"]["comparable_external_baselines"], 0)
        self.assertEqual(report["summary"]["non_comparable_baselines"], 1)
        comparable = next(item for item in report["comparisons"] if item["baseline_id"] == "ok-baseline")
        self.assertTrue(comparable["comparability"]["comparable"])
        self.assertGreater(comparable["wins"], 0)
        non_comparable = next(item for item in report["comparisons"] if item["baseline_id"] == "bad-baseline")
        self.assertFalse(non_comparable["comparability"]["comparable"])
        self.assertGreater(len(non_comparable["comparability"]["reasons"]), 0)
        self.assertFalse(non_comparable["verification"]["evidence_valid"])

    def test_external_verified_without_replication_is_not_comparable(self) -> None:
        registry_path = self.temp_dir / "frontier_baselines.json"
        registry = {
            "registry_version": "test-v1",
            "baselines": [
                {
                    "baseline_id": "external-no-replay",
                    "label": "External without replay",
                    "source_type": "external_reported",
                    "source": "test",
                    "source_date": "2026-02-17",
                    "verified": True,
                    "enabled": True,
                    "suite_id": "quantum_hard_suite_v2_adversarial",
                    "scoring_protocol": "src/agai/quantum_suite.py:263",
                    "evidence": {
                        "citation": "source paper",
                        "artifact_hash": "sha256:test",
                        "retrieval_date": "2026-02-17",
                        "verification_method": "manual extraction",
                        "replication_status": "pending",
                    },
                    "metrics": {"quality": 0.91},
                }
            ],
        }
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        eval_report = {
            "benchmark_provenance": {"scoring_reference": "src/agai/quantum_suite.py:263"},
            "benchmark_progress": {
                "suite_id": "quantum_hard_suite_v2_adversarial",
                "observed": {"quality": 0.92},
            },
        }
        report = DeclaredBaselineComparator(registry_path=str(registry_path)).compare(eval_report)
        self.assertEqual(report["summary"]["comparable_baselines"], 0)
        row = report["comparisons"][0]
        self.assertFalse(row["comparability"]["comparable"])
        self.assertIn("external baseline missing replicated-internal-harness status", row["comparability"]["reasons"])

    def test_compare_without_registry_file(self) -> None:
        eval_report = {
            "benchmark_provenance": {"scoring_reference": "src/agai/quantum_suite.py:263"},
            "benchmark_progress": {
                "suite_id": "quantum_hard_suite_v2_adversarial",
                "observed": {"quality": 0.9},
            },
        }
        report = DeclaredBaselineComparator(registry_path=str(self.temp_dir / "missing.json")).compare(eval_report)
        self.assertEqual(report["status"], "no_baselines_configured")
        self.assertEqual(report["summary"]["total_baselines"], 0)
        self.assertEqual(report["summary"]["comparable_external_baselines"], 0)


if __name__ == "__main__":
    unittest.main()
