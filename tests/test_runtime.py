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
        self.assertIn("hypothesis_sandbox", demo)
        self.assertIn("acceptance_rate", demo["hypothesis_sandbox"])
        self.assertIn("researcher_guidance", demo)
        self.assertIn("execution_dag", demo["researcher_guidance"])
        self.assertIn("execution_validation", demo["researcher_guidance"])
        self.assertTrue(demo["researcher_guidance"]["execution_validation"]["ok"])
        self.assertIn("qec_simulator_hook", demo["tool_reasoning"])
        qec_tool = demo["tool_reasoning"]["qec_simulator_hook"]
        self.assertTrue(qec_tool["ok"])
        self.assertIn("status", qec_tool["output"])
        self.assertIn("consistency", qec_tool["output"])
        self.assertTrue((self.temp_dir / "quantum_demo_output.json").exists())

        eval_report = runtime.run_quantum_hard_suite()
        self.assertIn("scorecard", eval_report)
        self.assertIn("holdout_scorecard", eval_report)
        self.assertIn("adversarial_scorecard", eval_report)
        self.assertIn("benchmark_provenance", eval_report)
        self.assertFalse(eval_report["benchmark_provenance"]["external_sota_comparable"])
        self.assertIn("disclaimer", eval_report["benchmark_provenance"])
        self.assertIn("suite_id", eval_report["benchmark_provenance"])
        self.assertIn("specialist_reference", eval_report)
        self.assertIn("public", eval_report["specialist_reference"])
        self.assertIn("holdout", eval_report["specialist_reference"])
        self.assertIn("adversarial", eval_report["specialist_reference"])
        self.assertIn("benchmark_progress", eval_report)
        self.assertIn("suite_id", eval_report["benchmark_progress"])
        self.assertIn("remaining_distance", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("case_margin_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("adversarial_quality_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("adversarial_split_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("public_holdout_overlap_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("public_adversarial_overlap_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("specialist_public_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("specialist_holdout_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("specialist_adversarial_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn(
            "min_specialist_adversarial_aggregate_delta",
            eval_report["benchmark_progress"]["targets"],
        )
        self.assertIn("max_public_adversarial_overlap", eval_report["benchmark_progress"]["targets"])
        self.assertIn("suite_leakage", eval_report["benchmark_progress"]["observed"])
        self.assertIn("benchmark_tracking", eval_report)
        self.assertIn("summary", eval_report["benchmark_tracking"])
        self.assertTrue((self.temp_dir / "benchmark_history.jsonl").exists())
        self.assertIn("moonshot_tracking", eval_report)
        self.assertIn("snapshot", eval_report["moonshot_tracking"])
        self.assertIn("summary", eval_report["moonshot_tracking"])
        self.assertFalse(eval_report["moonshot_tracking"]["summary"]["release_gate_enabled"])
        self.assertTrue((self.temp_dir / "moonshot_history.jsonl").exists())
        self.assertIn("failure_analysis", eval_report)
        self.assertIn("claim_calibration", eval_report)
        self.assertIn("declared_baseline_comparison", eval_report)
        self.assertIn("summary", eval_report["declared_baseline_comparison"])
        self.assertGreaterEqual(eval_report["declared_baseline_comparison"]["summary"]["total_baselines"], 1)
        self.assertIn("combined", eval_report["failure_analysis"])
        self.assertIn("public_overclaim_gap", eval_report["benchmark_progress"]["gaps"])
        self.assertIn("max_public_overclaim_rate", eval_report["benchmark_progress"]["targets"])

        distilled = runtime.run_trace_distillation()
        self.assertIn("policies", distilled)
        self.assertTrue((self.temp_dir / "distilled_policy.json").exists())

        scale_path = runtime.run_scale_path_decision_framework()
        self.assertIn("default_decision", scale_path)
        self.assertIn("scenario_analysis", scale_path)
        self.assertIn("recommended_profile", scale_path["default_decision"])
        self.assertTrue((self.temp_dir / "scale_path_decision.json").exists())


if __name__ == "__main__":
    unittest.main()
