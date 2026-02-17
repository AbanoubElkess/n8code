from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.adapters import HeuristicSmallModelAdapter
from agai.memory import ProvenanceMemory
from agai.orchestration import AgentRuntime, MultiAgentOrchestrator
from agai.types import AgentCard, TaskSpec


class TestOrchestration(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agai-test-"))
        self.memory = ProvenanceMemory(
            db_path=str(self.temp_dir / "m.sqlite"),
            trace_path=str(self.temp_dir / "trace.jsonl"),
        )
        self.agents = [
            AgentRuntime(
                card=AgentCard(
                    id="planner",
                    role="planner",
                    capabilities=["plan"],
                    budget_limit={"max_tokens": 1000},
                    safety_policy={"strict": True},
                    model_profile={"provider": "local"},
                ),
                adapter=HeuristicSmallModelAdapter(),
                system_prompt="You are planner.",
            ),
            AgentRuntime(
                card=AgentCard(
                    id="critic",
                    role="critic",
                    capabilities=["critique"],
                    budget_limit={"max_tokens": 1000},
                    safety_policy={"strict": True},
                    model_profile={"provider": "local"},
                ),
                adapter=HeuristicSmallModelAdapter(),
                system_prompt="You are critic.",
            ),
        ]
        self.orch = MultiAgentOrchestrator(self.agents, self.memory)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multi_agent_solve(self) -> None:
        task = TaskSpec(
            goal="Design a low-cost quantum decoder study.",
            constraints=["budget", "falsification"],
            success_metric="quality",
            budget={"max_tokens": 2500, "max_latency_ms": 50000, "max_energy_joules": 120, "max_usd": 0.1},
            deadline="now",
            domain="quantum",
        )
        result = self.orch.solve(task, rounds=2)
        self.assertIn("final_answer", result.outcomes)
        self.assertTrue(len(result.reproducibility_artifact_ids) >= 2)
        self.assertTrue(self.memory.db_path.exists())
        self.assertTrue(self.memory.trace_path.exists())

    def test_single_agent_baseline(self) -> None:
        task = TaskSpec(
            goal="Plan a constrained experiment.",
            constraints=["budget"],
            success_metric="quality",
            budget={"max_tokens": 1200, "max_latency_ms": 20000, "max_energy_joules": 60, "max_usd": 0.05},
            deadline="now",
            domain="science",
        )
        result = self.orch.run_single_agent_baseline(task, agent_id="planner")
        self.assertIn("final_answer", result.outcomes)
        self.assertEqual(result.contradictions, [])


if __name__ == "__main__":
    unittest.main()

