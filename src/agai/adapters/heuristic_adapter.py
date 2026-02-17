from __future__ import annotations

import re
from typing import Any

from ..model_adapter import BaseModelAdapter


class HeuristicSmallModelAdapter(BaseModelAdapter):
    """
    Fully local deterministic fallback adapter.
    Useful for low-cost baseline and tests when Ollama is unavailable.
    """

    def __init__(self, model_name: str = "heuristic-small-1") -> None:
        super().__init__(model_name=model_name)

    def _extract_role(self, prompt: str) -> str:
        match = re.search(r"Role:\s*(.+)", prompt)
        if not match:
            return "generalist"
        role = match.group(1).strip().lower()
        if "critic" in role:
            return "critic"
        if "physic" in role or "quantum" in role:
            return "physicist"
        if "planner" in role:
            return "planner"
        return "generalist"

    def generate(self, prompt: str, **kwargs: Any) -> str:
        start = self._start_timer()
        lower = prompt.lower()
        role = self._extract_role(prompt)
        sections = [
            "Proposal:",
            "Risks:",
            "Next experiment:",
            "Evidence keywords:",
        ]
        if "quantum" in lower or "syndrome" in lower:
            planner_proposal = (
                "Define a two-stage study: decoder selection followed by constrained ablation. "
                "Track logical error rate and latency under identical syndrome traces."
            )
            critic_proposal = (
                "Challenge baseline assumptions with counterexamples: test if claimed decoder gains "
                "vanish under shifted noise anisotropy or timing jitter."
            )
            physicist_proposal = (
                "Compare matching-based and belief-propagation decoders across syndrome depth sweeps; "
                "report logical error rate, runtime overhead, and ablation on control-field smoothness."
            )
            if role == "critic":
                proposal = critic_proposal
                risks = (
                    "Risk: apparent improvements may be artifact-driven. "
                    "Failure mode: non-stationary noise breaks decoder generalization."
                )
                experiment = (
                    "Run falsification with held-out noise profiles, then perform negative-control ablation "
                    "where no gain should appear."
                )
            elif role == "physicist":
                proposal = physicist_proposal
                risks = (
                    "Risk: lower logical error rate may trade off against runtime budget and calibration stability."
                )
                experiment = (
                    "Sweep coupling/frequency control parameters, execute syndrome decoding ablation, "
                    "and report confidence intervals with reproducible seeds."
                )
            else:
                proposal = planner_proposal
                risks = "Risk: over-optimization for one benchmark task can reduce generalization."
                experiment = (
                    "Start with coarse search, then narrow to top configurations using budget-aware branch pruning."
                )
            keywords = (
                "decoder, syndrome, logical error rate, latency, ablation, falsification, tradeoff, confidence interval"
            )
        else:
            proposal = "Use constrained multi-agent decomposition with explicit budget gates."
            risks = (
                "Risk: hidden assumptions can overfit prior beliefs; "
                "failure mode includes unstable conclusions under perturbation."
            )
            experiment = (
                "Execute falsification-first ablation across control parameters and report confidence intervals."
            )
            keywords = "cost, quality, reproducibility, novelty, falsification"
        output = "\n".join([sections[0], proposal, sections[1], risks, sections[2], experiment, sections[3], keywords])
        self._finalize_cost(prompt=prompt, output=output, start=start, usd_per_1k=0.0)
        return output
