from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ComputeDecision:
    depth: int
    branches: int
    early_exit: bool
    reason: str


class TestTimeComputeController:
    """
    Adaptive test-time compute policy for low-cost deployment.
    """

    def __init__(self, max_depth: int = 4, max_branches: int = 6) -> None:
        self.max_depth = max_depth
        self.max_branches = max_branches

    def decide(
        self,
        uncertainty: float,
        budget_ratio_remaining: float,
        recent_gain: float,
    ) -> ComputeDecision:
        uncertainty = max(0.0, min(1.0, uncertainty))
        budget_ratio_remaining = max(0.0, min(1.0, budget_ratio_remaining))
        recent_gain = max(-1.0, min(1.0, recent_gain))

        if budget_ratio_remaining < 0.15:
            return ComputeDecision(depth=1, branches=1, early_exit=True, reason="Budget-critical mode.")

        depth = 1 + int(round(uncertainty * (self.max_depth - 1)))
        branches = 1 + int(round(uncertainty * (self.max_branches - 1)))

        if recent_gain < 0.02 and uncertainty < 0.4:
            return ComputeDecision(depth=1, branches=1, early_exit=True, reason="Low marginal gain.")
        if recent_gain < 0.0:
            branches = max(1, branches - 1)

        return ComputeDecision(
            depth=min(depth, self.max_depth),
            branches=min(branches, self.max_branches),
            early_exit=False,
            reason="Adaptive compute expansion.",
        )

