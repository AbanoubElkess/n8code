from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.scale_path import ScalePathDecisionEngine


class TestScalePath(unittest.TestCase):
    def test_evaluate_returns_governance_and_calibration(self) -> None:
        engine = ScalePathDecisionEngine()
        decision = engine.evaluate(
            {
                "name": "strict-local",
                "privacy_level": "strict",
                "monthly_budget_usd": 120.0,
                "latency_sla_ms": 80_000,
                "offline_requirement": True,
                "regulatory_sensitivity": "high",
                "team_ops_capacity": "small",
                "workload_variability": "medium",
                "peak_task_complexity": "high",
            }
        )
        self.assertIn("recommended_profile", decision)
        self.assertIn("governance_policy", decision)
        self.assertIn("claim_calibration", decision)
        self.assertIn("profile_key", decision["recommended_profile"])
        self.assertGreaterEqual(decision["decision_confidence"], 0.5)

    def test_scenario_analysis_has_three_profiles(self) -> None:
        engine = ScalePathDecisionEngine()
        analysis = engine.scenario_analysis()
        self.assertIn("scenarios", analysis)
        self.assertEqual(len(analysis["scenarios"]), 3)
        self.assertEqual(analysis["summary"]["scenario_count"], 3)
        self.assertEqual(len(analysis["summary"]["recommended_paths"]), 3)

    def test_recommendation_buckets_are_disjoint(self) -> None:
        engine = ScalePathDecisionEngine()
        decision = engine.evaluate(
            {
                "name": "balanced",
                "privacy_level": "strict",
                "monthly_budget_usd": 250.0,
                "latency_sla_ms": 60_000,
                "offline_requirement": True,
                "regulatory_sensitivity": "medium",
                "team_ops_capacity": "medium",
                "workload_variability": "high",
                "peak_task_complexity": "high",
            }
        )
        alternatives = {row["profile_key"] for row in decision["alternative_profiles"]}
        rejected = {row["profile_key"] for row in decision["rejected_profiles"]}
        self.assertTrue(alternatives.isdisjoint(rejected))
        self.assertNotIn(decision["recommended_profile"]["profile_key"], alternatives)
        self.assertNotIn(decision["recommended_profile"]["profile_key"], rejected)


if __name__ == "__main__":
    unittest.main()
