from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.research_guidance import ResearchGuidanceEngine


class TestResearchGuidance(unittest.TestCase):
    def test_execution_dag_generation(self) -> None:
        engine = ResearchGuidanceEngine()
        plan, hypotheses = engine.build_experiment_plan(
            question="Design a low-cost falsifiable stabilizer schedule experiment.",
            domain="quantum-error-correction",
            constraints=["single-consumer-laptop", "falsification required"],
            budget={"max_tokens": 2400, "max_latency_ms": 40_000, "max_energy_joules": 120.0, "max_usd": 0.06},
        )
        dag = engine.latest_execution_dag()
        validation = engine.latest_execution_validation()

        self.assertGreater(len(hypotheses), 0)
        self.assertTrue(validation["ok"])
        self.assertGreaterEqual(dag["parallel_branch_count"], 1)
        self.assertEqual(dag["entry_node"], "N0_FORMALIZE")
        self.assertEqual(dag["terminal_node"], "N5_REPORT")
        self.assertGreater(plan.parameters["execution_dag_nodes"], 0)
        self.assertTrue(plan.parameters["execution_validation_ok"])

        simulation_nodes = [node for node in dag["nodes"] if str(node["id"]).startswith("N3_SIM_")]
        self.assertGreaterEqual(len(simulation_nodes), 1)
        self.assertTrue(all("N2_GATE" in node["depends_on"] for node in simulation_nodes))

    def test_execution_dag_validation_rejects_cycles(self) -> None:
        engine = ResearchGuidanceEngine()
        cyclic = {
            "entry_node": "A",
            "nodes": [
                {"id": "A", "depends_on": ["B"], "budget": {"max_tokens": 1, "max_latency_ms": 1, "max_energy_joules": 1, "max_usd": 1}},
                {"id": "B", "depends_on": ["A"], "budget": {"max_tokens": 1, "max_latency_ms": 1, "max_energy_joules": 1, "max_usd": 1}},
            ],
        }
        report = engine._validate_execution_dag(cyclic)
        self.assertFalse(report["ok"])
        self.assertTrue(any("cycle" in error.lower() for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()

