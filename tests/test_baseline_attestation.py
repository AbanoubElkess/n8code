from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.baseline_attestation import ExternalBaselineAttestationService


class TestExternalBaselineAttestationService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-baseline-attest-"))
        self.registry_path = self.temp_dir / "frontier_baselines.json"
        self.service = ExternalBaselineAttestationService(registry_path=str(self.registry_path))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_registry(self, baseline: dict[str, object]) -> None:
        payload = {
            "registry_version": "test",
            "baselines": [baseline],
        }
        self.registry_path.write_text(json.dumps(payload), encoding="utf-8")

    def _eval_report(self) -> dict[str, object]:
        return {
            "benchmark_progress": {
                "suite_id": "quantum_hard_suite_v2_adversarial",
                "observed": {
                    "quality": 0.9148,
                    "aggregate_delta": 0.4851,
                },
            },
            "benchmark_provenance": {
                "scoring_reference": "src/agai/quantum_suite.py:263",
            },
        }

    def test_attestation_passes_within_delta(self) -> None:
        baseline = {
            "baseline_id": "external-a",
            "label": "External A",
            "source_type": "external_reported",
            "source": "test",
            "source_date": "2026-02-17",
            "verified": False,
            "enabled": True,
            "suite_id": "quantum_hard_suite_v2_adversarial",
            "scoring_protocol": "src/agai/quantum_suite.py:263",
            "evidence": {
                "citation": "test citation",
                "artifact_hash": "sha256:test",
                "retrieval_date": "2026-02-17",
                "verification_method": "manual",
                "replication_status": "pending",
            },
            "metrics": {
                "quality": 0.9100,
                "aggregate_delta": 0.4800,
            },
            "notes": "",
        }
        self._write_registry(baseline)
        result = self.service.attest_from_eval_report(
            baseline_id="external-a",
            eval_report=self._eval_report(),
            max_metric_delta=0.02,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "attested")
        self.assertTrue(result["attestation_passed"])
        self.assertTrue(result["verified_effective"])
        self.assertEqual(result["replication_status"], "replicated-internal-harness")
        stored = json.loads(self.registry_path.read_text(encoding="utf-8"))
        row = stored["baselines"][0]
        self.assertTrue(row["verified"])
        self.assertEqual(row["evidence"]["replication_status"], "replicated-internal-harness")
        self.assertIn("attestation", row["evidence"])

    def test_attestation_fails_when_delta_exceeds_threshold(self) -> None:
        baseline = {
            "baseline_id": "external-b",
            "label": "External B",
            "source_type": "external_reported",
            "source": "test",
            "source_date": "2026-02-17",
            "verified": False,
            "enabled": True,
            "suite_id": "quantum_hard_suite_v2_adversarial",
            "scoring_protocol": "src/agai/quantum_suite.py:263",
            "evidence": {
                "citation": "test citation",
                "artifact_hash": "sha256:test",
                "retrieval_date": "2026-02-17",
                "verification_method": "manual",
                "replication_status": "pending",
            },
            "metrics": {
                "quality": 0.50,
            },
            "notes": "",
        }
        self._write_registry(baseline)
        result = self.service.attest_from_eval_report(
            baseline_id="external-b",
            eval_report=self._eval_report(),
            max_metric_delta=0.02,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "rejected")
        self.assertFalse(result["attestation_passed"])
        self.assertFalse(result["verified_effective"])
        self.assertEqual(result["replication_status"], "replication-failed")
        self.assertTrue(any("metric delta exceeds threshold for quality" in reason for reason in result["reasons"]))
        stored = json.loads(self.registry_path.read_text(encoding="utf-8"))
        row = stored["baselines"][0]
        self.assertFalse(row["verified"])
        self.assertEqual(row["evidence"]["replication_status"], "replication-failed")

    def test_attestation_rejects_non_external_baseline(self) -> None:
        baseline = {
            "baseline_id": "internal-c",
            "label": "Internal C",
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
                "verification_method": "manual",
                "replication_status": "replicated-internal-harness",
            },
            "metrics": {
                "quality": 0.91,
            },
            "notes": "",
        }
        self._write_registry(baseline)
        result = self.service.attest_from_eval_report(
            baseline_id="internal-c",
            eval_report=self._eval_report(),
            max_metric_delta=0.02,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "rejected")
        self.assertFalse(result["attestation_passed"])
        self.assertTrue(any("only allowed for external baselines" in reason for reason in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
