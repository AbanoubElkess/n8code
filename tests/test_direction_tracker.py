from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.direction_tracker import DirectionTracker


class TestDirectionTracker(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-direction-"))
        self.path = self.temp_dir / "direction_history.jsonl"
        self.tracker = DirectionTracker(history_path=str(self.path))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_and_summary(self) -> None:
        first = {
            "distance": {
                "internal_remaining_distance": 0.3,
                "external_claim_distance": 2,
                "total_claim_distance": 2,
                "max_total_claim_distance": 3,
                "total_progress_ratio": 0.3333333333333333,
                "projected_total_claim_distance": 1,
                "projected_total_progress_ratio": 0.6666666666666666,
                "public_overclaim_rate_gap": 0.02,
            },
            "direction": {
                "combined_average_reality_score": 0.88,
                "internal_ready": False,
                "external_claim_ready": False,
                "claim_scope": "not-ready-for-release-claims",
            },
        }
        second = {
            "distance": {
                "internal_remaining_distance": 0.0,
                "external_claim_distance": 1,
                "total_claim_distance": 1,
                "max_total_claim_distance": 3,
                "total_progress_ratio": 0.6666666666666666,
                "projected_total_claim_distance": 0,
                "projected_total_progress_ratio": 1.0,
                "public_overclaim_rate_gap": 0.0,
            },
            "direction": {
                "combined_average_reality_score": 0.94,
                "internal_ready": True,
                "external_claim_ready": False,
                "claim_scope": "internal-comparative-only",
            },
        }
        self.tracker.record(first)
        self.tracker.record(second)
        summary = self.tracker.summary()
        self.assertEqual(summary["count"], 2)
        self.assertAlmostEqual(summary["best_internal_distance"], 0.0)
        self.assertEqual(summary["best_external_claim_distance"], 1)
        self.assertEqual(summary["best_total_claim_distance"], 1)
        self.assertAlmostEqual(summary["best_reality_score"], 0.94)
        self.assertAlmostEqual(summary["best_total_progress_ratio"], 0.6666666666666666)
        self.assertGreater(summary["internal_distance_trend"], 0.0)
        self.assertGreater(summary["external_distance_trend"], 0.0)
        self.assertGreater(summary["total_distance_trend"], 0.0)
        self.assertGreater(summary["reality_score_trend"], 0.0)
        self.assertGreater(summary["total_progress_ratio_trend"], 0.0)


if __name__ == "__main__":
    unittest.main()
