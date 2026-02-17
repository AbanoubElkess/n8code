from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from .orchestration import MultiAgentOrchestrator
from .quantum_suite import default_quantum_suite, holdout_quantum_suite, score_quantum_answer
from .types import Scorecard, TaskSpec


class Evaluator:
    def __init__(self, benchmark_target_path: str = "config/benchmark_targets.json") -> None:
        self.benchmark_target_path = benchmark_target_path

    def _load_targets(self) -> dict[str, float]:
        default_targets = {
            "min_case_score": 0.62,
            "min_case_margin": 0.1,
            "min_pass_rate": 1.0,
            "min_quality": 0.8,
            "min_aggregate_delta": 0.3,
            "min_holdout_quality": 0.72,
            "max_public_holdout_quality_delta": 0.2,
        }
        path = Path(self.benchmark_target_path)
        if not path.exists():
            return default_targets
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            targets = payload.get("targets", {})
            return {
                "min_case_score": float(targets.get("min_case_score", default_targets["min_case_score"])),
                "min_case_margin": float(targets.get("min_case_margin", default_targets["min_case_margin"])),
                "min_pass_rate": float(targets.get("min_pass_rate", default_targets["min_pass_rate"])),
                "min_quality": float(targets.get("min_quality", default_targets["min_quality"])),
                "min_aggregate_delta": float(targets.get("min_aggregate_delta", default_targets["min_aggregate_delta"])),
                "min_holdout_quality": float(targets.get("min_holdout_quality", default_targets["min_holdout_quality"])),
                "max_public_holdout_quality_delta": float(
                    targets.get("max_public_holdout_quality_delta", default_targets["max_public_holdout_quality_delta"])
                ),
            }
        except Exception:  # noqa: BLE001
            return default_targets

    def _evaluate_split(
        self,
        cases: list,
        orchestrator: MultiAgentOrchestrator,
        baseline_agent_id: str,
        baseline_mode: str = "specialist",
    ) -> dict[str, object]:
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
            baseline = orchestrator.run_single_agent_baseline_with_mode(
                task,
                agent_id=baseline_agent_id,
                mode=baseline_mode,
            )

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
                    "baseline_mode": baseline_mode,
                    "delta": multi_score - base_score,
                    "passed": multi_score >= 0.62,
                }
            )

        aggregate_delta = (mean(multi_scores) - mean(baseline_scores)) if baseline_scores else 0.0
        pass_rate = (
            sum(1 for score in multi_scores if score >= 0.62) / len(multi_scores)
            if multi_scores
            else 0.0
        )
        scorecard = Scorecard(
            quality=mean(multi_scores) if multi_scores else 0.0,
            latency_ms=float(mean(latencies) if latencies else 0.0),
            cost_usd=float(mean(costs) if costs else 0.0),
            energy_joules=float(mean(energies) if energies else 0.0),
            reproducibility=max(0.0, 1.0 - (contradictions * 0.1)),
            novelty=min(1.0, 0.55 + aggregate_delta),
            notes=[
                f"average_multi_score={mean(multi_scores) if multi_scores else 0.0:.3f}",
                f"average_baseline_score={mean(baseline_scores) if baseline_scores else 0.0:.3f}",
            ],
        )
        return {
            "details": details,
            "aggregate_delta": aggregate_delta,
            "pass_rate": pass_rate,
            "scorecard": scorecard,
        }

    def evaluate_quantum_suite(
        self,
        orchestrator: MultiAgentOrchestrator,
        baseline_agent_id: str,
    ) -> dict[str, object]:
        public = self._evaluate_split(
            cases=default_quantum_suite(),
            orchestrator=orchestrator,
            baseline_agent_id=baseline_agent_id,
            baseline_mode="generalist",
        )
        holdout = self._evaluate_split(
            cases=holdout_quantum_suite(),
            orchestrator=orchestrator,
            baseline_agent_id=baseline_agent_id,
            baseline_mode="generalist",
        )
        specialist_reference = self._evaluate_split(
            cases=default_quantum_suite(),
            orchestrator=orchestrator,
            baseline_agent_id=baseline_agent_id,
            baseline_mode="specialist",
        )
        details = public["details"]
        scorecard = public["scorecard"]
        aggregate_delta = float(public["aggregate_delta"])
        pass_rate = float(public["pass_rate"])
        holdout_quality = float(holdout["scorecard"].quality)
        holdout_pass_rate = float(holdout["pass_rate"])
        split_quality_delta = abs(float(scorecard.quality) - holdout_quality)

        targets = self._load_targets()
        per_case_gap = [
            {
                "case_id": row["case_id"],
                "gap_to_min_case_score": max(0.0, float(targets["min_case_score"]) - float(row["multi_score"])),
                "margin_over_min_case_score": float(row["multi_score"]) - float(targets["min_case_score"]),
            }
            for row in details
        ]
        quality_gap = max(0.0, float(targets["min_quality"]) - float(scorecard.quality))
        pass_rate_gap = max(0.0, float(targets["min_pass_rate"]) - float(pass_rate))
        aggregate_delta_gap = max(0.0, float(targets["min_aggregate_delta"]) - float(aggregate_delta))
        holdout_quality_gap = max(0.0, float(targets["min_holdout_quality"]) - holdout_quality)
        split_delta_gap = max(0.0, split_quality_delta - float(targets["max_public_holdout_quality_delta"]))
        worst_case_margin = (
            min(row["margin_over_min_case_score"] for row in per_case_gap)
            if per_case_gap
            else -float(targets["min_case_margin"])
        )
        case_margin_gap = max(0.0, float(targets["min_case_margin"]) - float(worst_case_margin))
        remaining_distance = quality_gap + pass_rate_gap + aggregate_delta_gap + sum(
            row["gap_to_min_case_score"] for row in per_case_gap
        ) + case_margin_gap + holdout_quality_gap + split_delta_gap
        benchmark_progress = {
            "targets": targets,
            "observed": {
                "quality": scorecard.quality,
                "pass_rate": pass_rate,
                "aggregate_delta": aggregate_delta,
                "worst_case_margin": worst_case_margin,
                "holdout_quality": holdout_quality,
                "holdout_pass_rate": holdout_pass_rate,
                "split_quality_delta": split_quality_delta,
                "specialist_reference_aggregate_delta": float(specialist_reference["aggregate_delta"]),
            },
            "gaps": {
                "quality_gap": quality_gap,
                "pass_rate_gap": pass_rate_gap,
                "aggregate_delta_gap": aggregate_delta_gap,
                "case_margin_gap": case_margin_gap,
                "holdout_quality_gap": holdout_quality_gap,
                "split_delta_gap": split_delta_gap,
                "per_case_gap": per_case_gap,
                "remaining_distance": remaining_distance,
            },
            "ready": remaining_distance <= 1e-9,
        }

        return {
            "scorecard": scorecard.__dict__,
            "details": details,
            "aggregate_delta": aggregate_delta,
            "holdout_scorecard": holdout["scorecard"].__dict__,
            "holdout_details": holdout["details"],
            "holdout_aggregate_delta": float(holdout["aggregate_delta"]),
            "specialist_reference": {
                "scorecard": specialist_reference["scorecard"].__dict__,
                "details": specialist_reference["details"],
                "aggregate_delta": float(specialist_reference["aggregate_delta"]),
            },
            "benchmark_progress": benchmark_progress,
        }
