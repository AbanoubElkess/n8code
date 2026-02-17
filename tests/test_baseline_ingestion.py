from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.baseline_ingestion import ExternalBaselineIngestionService


class TestExternalBaselineIngestionService(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-baseline-ingest-"))
        self.registry_path = self.temp_dir / "frontier_baselines.json"
        self.input_path = self.temp_dir / "ingest_input.json"
        self.service = ExternalBaselineIngestionService(registry_path=str(self.registry_path))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ingest_downgrades_verified_without_replication(self) -> None:
        payload = {
            "baseline_id": "external-sample-a",
            "label": "External Sample A",
            "source_type": "external_reported",
            "source": "example",
            "source_date": "2026-02-17",
            "verified": True,
            "enabled": True,
            "suite_id": "quantum_hard_suite_v2_adversarial",
            "scoring_protocol": "src/agai/quantum_suite.py:263",
            "evidence": {
                "citation": "example citation",
                "retrieval_date": "2026-02-17",
                "verification_method": "manual extraction",
                "replication_status": "pending",
            },
            "metrics": {"quality": 0.9},
        }
        self.input_path.write_text(json.dumps(payload), encoding="utf-8")
        result = self.service.ingest_file(str(self.input_path))
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["verified_effective"])
        self.assertEqual(result["replication_status"], "pending")
        self.assertTrue(any("downgraded" in warning for warning in result["warnings"]))

        stored = json.loads(self.registry_path.read_text(encoding="utf-8"))
        row = stored["baselines"][0]
        self.assertFalse(row["verified"])
        self.assertIn("artifact_hash", row["evidence"])
        self.assertTrue(str(row["evidence"]["artifact_hash"]).startswith("sha256:"))

    def test_ingest_rejects_missing_evidence_fields(self) -> None:
        payload = {
            "baseline_id": "external-invalid",
            "label": "External Invalid",
            "source_type": "external_reported",
            "source": "example",
            "source_date": "2026-02-17",
            "verified": False,
            "enabled": True,
            "suite_id": "quantum_hard_suite_v2_adversarial",
            "scoring_protocol": "src/agai/quantum_suite.py:263",
            "evidence": {
                "citation": "",
                "retrieval_date": "2026-02-17",
                "verification_method": "",
            },
            "metrics": {"quality": 0.9},
        }
        self.input_path.write_text(json.dumps(payload), encoding="utf-8")
        result = self.service.ingest_file(str(self.input_path))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "validation failed")
        self.assertIn("evidence.citation is required", result["errors"])
        self.assertIn("evidence.verification_method is required", result["errors"])
        self.assertFalse(self.registry_path.exists())

    def test_ingest_updates_existing_baseline(self) -> None:
        initial = {
            "registry_version": "test",
            "baselines": [
                {
                    "baseline_id": "external-sample-b",
                    "label": "Old",
                    "source_type": "external_reported",
                    "source": "old",
                    "source_date": "2026-02-16",
                    "verified": False,
                    "enabled": True,
                    "suite_id": "quantum_hard_suite_v2_adversarial",
                    "scoring_protocol": "src/agai/quantum_suite.py:263",
                    "evidence": {
                        "citation": "old citation",
                        "artifact_hash": "sha256:old",
                        "retrieval_date": "2026-02-16",
                        "verification_method": "old method",
                        "replication_status": "pending",
                    },
                    "metrics": {"quality": 0.8},
                    "notes": "",
                }
            ],
        }
        self.registry_path.write_text(json.dumps(initial), encoding="utf-8")
        payload = {
            "baseline_id": "external-sample-b",
            "label": "New",
            "source_type": "external_reported",
            "source": "new",
            "source_date": "2026-02-17",
            "verified": True,
            "enabled": True,
            "suite_id": "quantum_hard_suite_v2_adversarial",
            "scoring_protocol": "src/agai/quantum_suite.py:263",
            "evidence": {
                "citation": "new citation",
                "artifact_hash": "sha256:new",
                "retrieval_date": "2026-02-17",
                "verification_method": "replay",
                "replication_status": "replicated-internal-harness",
            },
            "metrics": {"quality": 0.91},
        }
        self.input_path.write_text(json.dumps(payload), encoding="utf-8")
        result = self.service.ingest_file(str(self.input_path))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "updated")
        self.assertTrue(result["verified_effective"])

        stored = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(len(stored["baselines"]), 1)
        self.assertEqual(stored["baselines"][0]["label"], "New")
        self.assertTrue(stored["baselines"][0]["verified"])


if __name__ == "__main__":
    unittest.main()
