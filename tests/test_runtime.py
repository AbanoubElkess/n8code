from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.runtime import AgenticRuntime


class TestRuntime(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-runtime-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_market_and_quantum_paths(self) -> None:
        runtime = AgenticRuntime(use_ollama=False, artifacts_dir=str(self.temp_dir))
        market = runtime.generate_market_gap_report()
        self.assertIn("opportunities", market)

        demo = runtime.run_quantum_research_demo(
            "Propose a falsifiable strategy to reduce logical error rate under tight compute."
        )
        self.assertIn("result", demo)
        self.assertIn("tool_reasoning", demo)
        self.assertIn("qec_simulator_hook", demo["tool_reasoning"])
        self.assertTrue((self.temp_dir / "quantum_demo_output.json").exists())

        eval_report = runtime.run_quantum_hard_suite()
        self.assertIn("scorecard", eval_report)
        self.assertIn("holdout_scorecard", eval_report)
        self.assertIn("specialist_reference", eval_report)
        self.assertIn("public", eval_report["specialist_reference"])
        self.assertIn("holdout", eval_report["specialist_reference"])
        self.assertIn("benchmark_progress", eval_report)
        self.assertIn("remaining_distance", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("case_margin_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("specialist_public_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("specialist_holdout_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("benchmark_tracking", eval_report)
        self.assertIn("summary", eval_report["benchmark_tracking"])
        self.assertTrue((self.temp_dir / "benchmark_history.jsonl").exists())

        distilled = runtime.run_trace_distillation()
        self.assertIn("policies", distilled)
        self.assertTrue((self.temp_dir / "distilled_policy.json").exists())


if __name__ == "__main__":
    unittest.main()
