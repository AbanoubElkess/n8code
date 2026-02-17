from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.moonshot_tracker import MoonshotTracker


class TestMoonshotTracker(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-moonshot-"))
        self.path = self.temp_dir / "moonshot_history.jsonl"
        self.tracker = MoonshotTracker(history_path=str(self.path), policy_path="config/repro_policy.json")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_and_summary(self) -> None:
        sample = {
            "benchmark_progress": {
                "suite_id": "quantum_hard_suite_v2_adversarial",
                "observed": {"quality": 0.9},
                "gaps": {"remaining_distance": 0.0},
            },
            "declared_baseline_comparison": {
                "comparisons": [
                    {
                        "source_type": "internal_reference",
                        "mean_advantage": 0.11,
                        "comparability": {"comparable": True},
                    }
                ]
            },
        }
        self.tracker.record(sample)
        sample["declared_baseline_comparison"]["comparisons"][0]["mean_advantage"] = 0.13
        self.tracker.record(sample)

        summary = self.tracker.summary()
        self.assertEqual(summary["count"], 2)
        self.assertFalse(summary["release_gate_enabled"])
        self.assertGreater(summary["best_signal"], 0.0)
        self.assertGreater(summary["signal_trend"], 0.0)

    def test_summary_without_rows(self) -> None:
        tracker = MoonshotTracker(
            history_path=str(self.temp_dir / "missing_history.jsonl"),
            policy_path="config/repro_policy.json",
        )
        summary = tracker.summary()
        self.assertEqual(summary["count"], 0)
        self.assertFalse(summary["release_gate_enabled"])
        self.assertEqual(summary["status"], "tracking-only")


if __name__ == "__main__":
    unittest.main()
