from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from agai.compute_controller import TestTimeComputeController
from agai.cost_governor import CostGovernor
from agai.types import CostMeter


class TestCostAndCompute(unittest.TestCase):
    def test_budget_guard(self) -> None:
        governor = CostGovernor(max_tokens=100, max_latency_ms=2000, max_energy_joules=10.0, max_usd=0.01)
        self.assertTrue(governor.can_spend(CostMeter(tokens_in=10, tokens_out=20, latency_ms=1000, energy_joules=1, usd_cost=0.001)))
        governor.register(CostMeter(tokens_in=10, tokens_out=20, latency_ms=1000, energy_joules=1, usd_cost=0.001))
        self.assertFalse(governor.can_spend(CostMeter(tokens_in=90, tokens_out=90, latency_ms=100, energy_joules=1, usd_cost=0.001)))

    def test_compute_policy(self) -> None:
        policy = TestTimeComputeController(max_depth=4, max_branches=6)
        decision = policy.decide(uncertainty=0.8, budget_ratio_remaining=0.8, recent_gain=0.05)
        self.assertGreaterEqual(decision.depth, 2)
        critical = policy.decide(uncertainty=0.8, budget_ratio_remaining=0.1, recent_gain=0.05)
        self.assertTrue(critical.early_exit)


if __name__ == "__main__":
    unittest.main()

