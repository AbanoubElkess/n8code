from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.benchmark_tracker import BenchmarkTracker


class TestBenchmarkTracker(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-bench-"))
        self.path = self.temp_dir / "benchmark_history.jsonl"
        self.tracker = BenchmarkTracker(history_path=str(self.path))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_and_summary(self) -> None:
        sample = {
            "benchmark_progress": {
                "observed": {"quality": 0.9, "pass_rate": 1.0, "aggregate_delta": 0.3},
                "gaps": {"remaining_distance": 0.1},
                "ready": False,
            }
        }
        self.tracker.record(sample)
        sample["benchmark_progress"]["gaps"]["remaining_distance"] = 0.0
        sample["benchmark_progress"]["ready"] = True
        self.tracker.record(sample)

        summary = self.tracker.summary()
        self.assertEqual(summary["count"], 2)
        self.assertAlmostEqual(summary["best_quality"], 0.9)
        self.assertAlmostEqual(summary["best_distance"], 0.0)
        self.assertGreater(summary["distance_trend"], 0.0)


if __name__ == "__main__":
    unittest.main()

