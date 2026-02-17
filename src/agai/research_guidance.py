from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .hypothesis import HypothesisExplorer
from .types import ExperimentPlan, HypothesisProgram


class ResearchGuidanceEngine:
    def __init__(self, explorer: Optional[HypothesisExplorer] = None) -> None:
        self.explorer = explorer or HypothesisExplorer()
        self._last_sandbox_report: dict[str, Any] = {}

    def build_experiment_plan(
        self,
        question: str,
        domain: str,
        constraints: list[str],
    ) -> tuple[ExperimentPlan, list[dict[str, Any]]]:
        seed = HypothesisProgram(
            rules=[
                f"Primary objective for {domain}: {question}",
                "Minimize logical error rate while preserving practical runtime.",
            ],
            priors={"known-physics-consistency": 0.8, "novelty-drive": 0.6},
            provenance=[f"generated:{datetime.utcnow().isoformat()}"],
        )
        sandbox = self.explorer.sandbox(seed_program=seed, limit=10, top_k=4)
        self._last_sandbox_report = sandbox
        ranked = sandbox.get("ranked_candidates", [])
        accepted_count = int(sandbox.get("accepted_count", 0))
        rejected_count = int(sandbox.get("rejected_count", 0))
        experiment = ExperimentPlan(
            simulator="qec-sim-lite",
            tool_chain=["literature-retrieval", "symbolic-checker", "qec-simulator", "statistical-validator"],
            parameters={
                "question": question,
                "domain": domain,
                "constraints": constraints,
                "num_hypotheses": len(ranked),
                "top_k": 4,
                "accepted_hypotheses": accepted_count,
                "rejected_hypotheses": rejected_count,
                "family_coverage": sandbox.get("family_coverage", {}),
            },
            stop_criteria={
                "max_runs": 60,
                "stability_delta": 0.03,
                "budget_guard": "strict",
                "min_acceptance_rate": 0.35,
            },
            steps=[
                "Formalize assumptions and target metric.",
                "Generate counterfactual hypotheses with control parameters.",
                "Run strict falsification gate and reject hard-invariant violations before simulation.",
                "Execute simulation and compare against baseline.",
                "Report confidence intervals, contradictions, and rejected-rule diagnostics.",
            ],
        )
        return experiment, [dict(item) for item in ranked]

    def latest_sandbox_report(self) -> dict[str, Any]:
        return dict(self._last_sandbox_report)
