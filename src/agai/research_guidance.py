from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional

from .hypothesis import HypothesisExplorer
from .types import ExperimentPlan, HypothesisProgram


class ResearchGuidanceEngine:
    def __init__(self, explorer: Optional[HypothesisExplorer] = None) -> None:
        self.explorer = explorer or HypothesisExplorer()

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
        candidates = self.explorer.propose_counterfactuals(seed, limit=6)
        ranked = self.explorer.rank(candidates)
        experiment = ExperimentPlan(
            simulator="qec-sim-lite",
            tool_chain=["literature-retrieval", "symbolic-checker", "qec-simulator", "statistical-validator"],
            parameters={
                "question": question,
                "domain": domain,
                "constraints": constraints,
                "num_hypotheses": len(ranked),
                "top_k": 3,
            },
            stop_criteria={
                "max_runs": 60,
                "stability_delta": 0.03,
                "budget_guard": "strict",
            },
            steps=[
                "Formalize assumptions and target metric.",
                "Generate counterfactual hypotheses with control parameters.",
                "Run falsification gate before simulation.",
                "Execute simulation and compare against baseline.",
                "Report confidence intervals and contradictions.",
            ],
        )
        return experiment, [asdict(item) for item in ranked]
