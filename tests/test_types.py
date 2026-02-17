from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.types import AgentCard, CostMeter, EvalCase, ExperimentPlan, MessageEnvelope, MessageIntent, TaskSpec


class TestTypes(unittest.TestCase):
    def test_cost_meter_add(self) -> None:
        left = CostMeter(tokens_in=2, tokens_out=3, latency_ms=4, energy_joules=0.4, usd_cost=0.01)
        right = CostMeter(tokens_in=5, tokens_out=7, latency_ms=8, energy_joules=0.6, usd_cost=0.02)
        merged = left.add(right)
        self.assertEqual(merged.tokens_in, 7)
        self.assertEqual(merged.tokens_out, 10)
        self.assertEqual(merged.latency_ms, 12)
        self.assertAlmostEqual(merged.energy_joules, 1.0)
        self.assertAlmostEqual(merged.usd_cost, 0.03)

    def test_dataclass_contracts(self) -> None:
        card = AgentCard(
            id="planner",
            role="planner",
            capabilities=["plan"],
            budget_limit={"max_tokens": 1000},
            safety_policy={"require_falsification": True},
            model_profile={"provider": "local"},
        )
        task = TaskSpec(
            goal="solve",
            constraints=["low-cost"],
            success_metric="quality",
            budget={"max_tokens": 1000},
            deadline="now",
            domain="science",
        )
        message = MessageEnvelope(
            sender=card.id,
            receiver="coordinator",
            intent=MessageIntent.PROPOSE,
            content="proposal",
            evidence_refs=[],
            confidence=0.7,
            cost_spent=CostMeter(),
        )
        case = EvalCase(case_id="E1", prompt="p", expected="e", domain="d", tags=["t"])
        plan = ExperimentPlan(
            simulator="sim",
            tool_chain=["tool"],
            parameters={"a": 1},
            stop_criteria={"max": 1},
            steps=["one"],
        )
        self.assertEqual(message.sender, "planner")
        self.assertEqual(task.domain, "science")
        self.assertEqual(case.case_id, "E1")
        self.assertEqual(plan.simulator, "sim")


if __name__ == "__main__":
    unittest.main()

