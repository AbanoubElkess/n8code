from __future__ import annotations

from statistics import mean

from .orchestration import MultiAgentOrchestrator
from .quantum_suite import default_quantum_suite, score_quantum_answer
from .types import Scorecard, TaskSpec


class Evaluator:
    def evaluate_quantum_suite(
        self,
        orchestrator: MultiAgentOrchestrator,
        baseline_agent_id: str,
    ) -> dict[str, object]:
        cases = default_quantum_suite()
        multi_scores: list[float] = []
        baseline_scores: list[float] = []
        latencies: list[int] = []
        costs: list[float] = []
        energies: list[float] = []
        contradictions = 0
        details: list[dict[str, object]] = []

        for case in cases:
            task = TaskSpec(
                goal=case.prompt,
                constraints=["single-consumer-laptop", "strict budget", "falsification required"],
                success_metric="absolute-win-on-defined-hard-suite",
                budget={"max_tokens": 3500, "max_latency_ms": 80_000, "max_energy_joules": 220.0, "max_usd": 0.12},
                deadline="immediate",
                domain=case.domain,
            )
            multi = orchestrator.solve(task, rounds=2)
            baseline = orchestrator.run_single_agent_baseline(task, agent_id=baseline_agent_id)

            multi_answer = str(multi.outcomes.get("final_answer", ""))
            base_answer = str(baseline.outcomes.get("final_answer", ""))
            multi_score = score_quantum_answer(case.expected, multi_answer)
            base_score = score_quantum_answer(case.expected, base_answer)
            multi_scores.append(multi_score)
            baseline_scores.append(base_score)

            budget = multi.outcomes.get("budget_spent", {})
            latencies.append(int(budget.get("latency_ms", 0)))
            costs.append(float(budget.get("usd_cost", 0.0)))
            energies.append(float(budget.get("energy_joules", 0.0)))
            contradictions += len(multi.contradictions)

            details.append(
                {
                    "case_id": case.case_id,
                    "multi_score": multi_score,
                    "baseline_score": base_score,
                    "delta": multi_score - base_score,
                    "passed": multi_score >= 0.62,
                }
            )

        scorecard = Scorecard(
            quality=mean(multi_scores) if multi_scores else 0.0,
            latency_ms=float(mean(latencies) if latencies else 0.0),
            cost_usd=float(mean(costs) if costs else 0.0),
            energy_joules=float(mean(energies) if energies else 0.0),
            reproducibility=max(0.0, 1.0 - (contradictions * 0.1)),
            novelty=min(1.0, 0.55 + (mean(multi_scores) - mean(baseline_scores) if baseline_scores else 0.0)),
            notes=[
                f"average_multi_score={mean(multi_scores) if multi_scores else 0.0:.3f}",
                f"average_baseline_score={mean(baseline_scores) if baseline_scores else 0.0:.3f}",
            ],
        )

        return {
            "scorecard": scorecard.__dict__,
            "details": details,
            "aggregate_delta": (mean(multi_scores) - mean(baseline_scores)) if baseline_scores else 0.0,
        }

