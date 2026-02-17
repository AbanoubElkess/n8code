from __future__ import annotations

from dataclasses import dataclass

from .types import CostMeter


@dataclass
class BudgetState:
    max_tokens: int
    max_latency_ms: int
    max_energy_joules: float
    max_usd: float
    spent: CostMeter


class CostGovernor:
    def __init__(
        self,
        max_tokens: int,
        max_latency_ms: int,
        max_energy_joules: float,
        max_usd: float,
    ) -> None:
        self._state = BudgetState(
            max_tokens=max_tokens,
            max_latency_ms=max_latency_ms,
            max_energy_joules=max_energy_joules,
            max_usd=max_usd,
            spent=CostMeter(),
        )

    @classmethod
    def from_budget(cls, budget: dict[str, float]) -> "CostGovernor":
        return cls(
            max_tokens=int(budget.get("max_tokens", 4000)),
            max_latency_ms=int(budget.get("max_latency_ms", 90_000)),
            max_energy_joules=float(budget.get("max_energy_joules", 300.0)),
            max_usd=float(budget.get("max_usd", 0.20)),
        )

    def can_spend(self, candidate: CostMeter) -> bool:
        projected_tokens = (
            self._state.spent.tokens_in
            + self._state.spent.tokens_out
            + candidate.tokens_in
            + candidate.tokens_out
        )
        projected_latency = self._state.spent.latency_ms + candidate.latency_ms
        projected_energy = self._state.spent.energy_joules + candidate.energy_joules
        projected_usd = self._state.spent.usd_cost + candidate.usd_cost
        return (
            projected_tokens <= self._state.max_tokens
            and projected_latency <= self._state.max_latency_ms
            and projected_energy <= self._state.max_energy_joules
            and projected_usd <= self._state.max_usd
        )

    def register(self, usage: CostMeter) -> None:
        self._state.spent = self._state.spent.add(usage)

    def remaining(self) -> dict[str, float]:
        spent_tokens = self._state.spent.tokens_in + self._state.spent.tokens_out
        return {
            "tokens": float(self._state.max_tokens - spent_tokens),
            "latency_ms": float(self._state.max_latency_ms - self._state.spent.latency_ms),
            "energy_joules": self._state.max_energy_joules - self._state.spent.energy_joules,
            "usd": self._state.max_usd - self._state.spent.usd_cost,
        }

    @property
    def spent(self) -> CostMeter:
        return self._state.spent

