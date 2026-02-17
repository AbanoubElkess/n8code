from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from .orchestration import MultiAgentOrchestrator
from .quantum_suite import (
    adversarial_quantum_suite,
    default_quantum_suite,
    holdout_quantum_suite,
    score_quantum_answer,
    suite_leakage_report,
)
from .reality_guard import RealityGuard
from .types import Scorecard, TaskSpec


class Evaluator:
    def __init__(self, benchmark_target_path: str = "config/benchmark_targets.json") -> None:
        self.benchmark_target_path = benchmark_target_path
        self.reality_guard = RealityGuard()

    def _load_targets(self) -> dict[str, float]:
        default_targets = {
            "min_case_score": 0.62,
            "min_case_margin": 0.1,
            "min_pass_rate": 1.0,
            "min_quality": 0.8,
            "min_aggregate_delta": 0.3,
            "min_holdout_quality": 0.72,
            "max_public_holdout_quality_delta": 0.2,
            "min_adversarial_quality": 0.7,
            "min_adversarial_pass_rate": 1.0,
            "max_public_adversarial_quality_delta": 0.25,
            "max_public_holdout_overlap": 0.5,
            "max_public_adversarial_overlap": 0.4,
            "max_holdout_adversarial_overlap": 0.45,
            "max_public_overclaim_rate": 0.05,
            "max_holdout_overclaim_rate": 0.08,
            "max_adversarial_overclaim_rate": 0.10,
            "min_specialist_public_aggregate_delta": 0.0,
            "min_specialist_holdout_aggregate_delta": 0.0,
            "min_specialist_adversarial_aggregate_delta": 0.0,
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
                "min_adversarial_quality": float(
                    targets.get("min_adversarial_quality", default_targets["min_adversarial_quality"])
                ),
                "min_adversarial_pass_rate": float(
                    targets.get("min_adversarial_pass_rate", default_targets["min_adversarial_pass_rate"])
                ),
                "max_public_adversarial_quality_delta": float(
                    targets.get(
                        "max_public_adversarial_quality_delta",
                        default_targets["max_public_adversarial_quality_delta"],
                    )
                ),
                "max_public_holdout_overlap": float(
                    targets.get("max_public_holdout_overlap", default_targets["max_public_holdout_overlap"])
                ),
                "max_public_adversarial_overlap": float(
                    targets.get("max_public_adversarial_overlap", default_targets["max_public_adversarial_overlap"])
                ),
                "max_holdout_adversarial_overlap": float(
                    targets.get("max_holdout_adversarial_overlap", default_targets["max_holdout_adversarial_overlap"])
                ),
                "max_public_overclaim_rate": float(
                    targets.get("max_public_overclaim_rate", default_targets["max_public_overclaim_rate"])
                ),
                "max_holdout_overclaim_rate": float(
                    targets.get("max_holdout_overclaim_rate", default_targets["max_holdout_overclaim_rate"])
                ),
                "max_adversarial_overclaim_rate": float(
                    targets.get("max_adversarial_overclaim_rate", default_targets["max_adversarial_overclaim_rate"])
                ),
                "min_specialist_public_aggregate_delta": float(
                    targets.get(
                        "min_specialist_public_aggregate_delta",
                        default_targets["min_specialist_public_aggregate_delta"],
                    )
                ),
                "min_specialist_holdout_aggregate_delta": float(
                    targets.get(
                        "min_specialist_holdout_aggregate_delta",
                        default_targets["min_specialist_holdout_aggregate_delta"],
                    )
                ),
                "min_specialist_adversarial_aggregate_delta": float(
                    targets.get(
                        "min_specialist_adversarial_aggregate_delta",
                        default_targets["min_specialist_adversarial_aggregate_delta"],
                    )
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
        overclaim_cases = 0
        overclaim_hits_total = 0
        details: list[dict[str, object]] = []
        failure_taxonomy = {
            "quality_below_threshold": 0,
            "overclaiming": 0,
            "contradiction_detected": 0,
            "budget_limit_triggered": 0,
        }

        for case in cases:
            task = TaskSpec(
                goal=case.prompt,
                constraints=["single-consumer-laptop", "strict budget", "falsification required"],
                success_metric="measurable-improvement-on-defined-hard-suite",
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
            claim_audit = self.reality_guard.audit_text(multi_answer)
            case_overclaim_hits = int(claim_audit.get("overclaim_hits", 0))
            overclaim_hits_total += case_overclaim_hits
            if case_overclaim_hits > 0:
                overclaim_cases += 1
            multi_scores.append(multi_score)
            baseline_scores.append(base_score)

            budget = multi.outcomes.get("budget_spent", {})
            latencies.append(int(budget.get("latency_ms", 0)))
            costs.append(float(budget.get("usd_cost", 0.0)))
            energies.append(float(budget.get("energy_joules", 0.0)))
            contradictions += len(multi.contradictions)
            has_budget_limit = "budget exceeded" in multi_answer.lower()
            if multi_score < 0.62:
                failure_taxonomy["quality_below_threshold"] += 1
            if case_overclaim_hits > 0:
                failure_taxonomy["overclaiming"] += 1
            if len(multi.contradictions) > 0:
                failure_taxonomy["contradiction_detected"] += 1
            if has_budget_limit:
                failure_taxonomy["budget_limit_triggered"] += 1

            details.append(
                {
                    "case_id": case.case_id,
                    "multi_score": multi_score,
                    "baseline_score": base_score,
                    "baseline_mode": baseline_mode,
                    "delta": multi_score - base_score,
                    "passed": multi_score >= 0.62,
                    "overclaim_hits": case_overclaim_hits,
                    "overclaim_terms": claim_audit.get("overclaim_terms", []),
                    "reality_score": claim_audit.get("reality_score", 0.0),
                }
            )

        aggregate_delta = (mean(multi_scores) - mean(baseline_scores)) if baseline_scores else 0.0
        overclaim_rate = (overclaim_cases / len(details)) if details else 0.0
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
                f"overclaim_rate={overclaim_rate:.3f}",
            ],
        )
        return {
            "details": details,
            "aggregate_delta": aggregate_delta,
            "pass_rate": pass_rate,
            "overclaim_rate": overclaim_rate,
            "failure_taxonomy": failure_taxonomy,
            "overclaim_hits_total": overclaim_hits_total,
            "scorecard": scorecard,
        }

    def _benchmark_provenance(self) -> dict[str, object]:
        public_cases = default_quantum_suite()
        holdout_cases = holdout_quantum_suite()
        adversarial_cases = adversarial_quantum_suite()
        return {
            "harness_type": "internal_deterministic_suite",
            "external_sota_comparable": False,
            "disclaimer": (
                "Scores are generated by the repository's internal quantum hard-suite harness and should not be "
                "presented as external leaderboard results."
            ),
            "scoring_reference": "src/agai/quantum_suite.py:263",
            "suite_reference": "src/agai/quantum_suite.py:147",
            "baseline_reference": "src/agai/orchestration.py:182",
            "suite_splits": {
                "public": {"count": len(public_cases), "case_ids": [case.case_id for case in public_cases]},
                "holdout": {"count": len(holdout_cases), "case_ids": [case.case_id for case in holdout_cases]},
                "adversarial": {"count": len(adversarial_cases), "case_ids": [case.case_id for case in adversarial_cases]},
            },
            "baseline_modes": {
                "generalist": "single-agent generic baseline",
                "specialist": "single-agent domain-specialized baseline",
            },
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
        adversarial = self._evaluate_split(
            cases=adversarial_quantum_suite(),
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
        specialist_reference_holdout = self._evaluate_split(
            cases=holdout_quantum_suite(),
            orchestrator=orchestrator,
            baseline_agent_id=baseline_agent_id,
            baseline_mode="specialist",
        )
        specialist_reference_adversarial = self._evaluate_split(
            cases=adversarial_quantum_suite(),
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
        adversarial_quality = float(adversarial["scorecard"].quality)
        adversarial_pass_rate = float(adversarial["pass_rate"])
        public_overclaim_rate = float(public["overclaim_rate"])
        holdout_overclaim_rate = float(holdout["overclaim_rate"])
        adversarial_overclaim_rate = float(adversarial["overclaim_rate"])
        split_quality_delta = abs(float(scorecard.quality) - holdout_quality)
        adversarial_split_quality_delta = abs(float(scorecard.quality) - adversarial_quality)
        leakage = suite_leakage_report()

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
        adversarial_quality_gap = max(0.0, float(targets["min_adversarial_quality"]) - adversarial_quality)
        adversarial_pass_rate_gap = max(0.0, float(targets["min_adversarial_pass_rate"]) - adversarial_pass_rate)
        adversarial_split_gap = max(
            0.0,
            adversarial_split_quality_delta - float(targets["max_public_adversarial_quality_delta"]),
        )
        public_holdout_overlap_gap = max(
            0.0,
            float(leakage["public_vs_holdout"]["mean_best_overlap"]) - float(targets["max_public_holdout_overlap"]),
        )
        public_adversarial_overlap_gap = max(
            0.0,
            float(leakage["public_vs_adversarial"]["mean_best_overlap"])
            - float(targets["max_public_adversarial_overlap"]),
        )
        holdout_adversarial_overlap_gap = max(
            0.0,
            float(leakage["holdout_vs_adversarial"]["mean_best_overlap"])
            - float(targets["max_holdout_adversarial_overlap"]),
        )
        public_overclaim_gap = max(0.0, public_overclaim_rate - float(targets["max_public_overclaim_rate"]))
        holdout_overclaim_gap = max(0.0, holdout_overclaim_rate - float(targets["max_holdout_overclaim_rate"]))
        adversarial_overclaim_gap = max(
            0.0,
            adversarial_overclaim_rate - float(targets["max_adversarial_overclaim_rate"]),
        )
        specialist_public_gap = max(
            0.0,
            float(targets["min_specialist_public_aggregate_delta"]) - float(specialist_reference["aggregate_delta"]),
        )
        specialist_holdout_gap = max(
            0.0,
            float(targets["min_specialist_holdout_aggregate_delta"]) - float(specialist_reference_holdout["aggregate_delta"]),
        )
        specialist_adversarial_gap = max(
            0.0,
            float(targets["min_specialist_adversarial_aggregate_delta"])
            - float(specialist_reference_adversarial["aggregate_delta"]),
        )
        worst_case_margin = (
            min(row["margin_over_min_case_score"] for row in per_case_gap)
            if per_case_gap
            else -float(targets["min_case_margin"])
        )
        case_margin_gap = max(0.0, float(targets["min_case_margin"]) - float(worst_case_margin))
        remaining_distance = (
            quality_gap
            + pass_rate_gap
            + aggregate_delta_gap
            + sum(row["gap_to_min_case_score"] for row in per_case_gap)
            + case_margin_gap
            + holdout_quality_gap
            + split_delta_gap
            + adversarial_quality_gap
            + adversarial_pass_rate_gap
            + adversarial_split_gap
            + public_holdout_overlap_gap
            + public_adversarial_overlap_gap
            + holdout_adversarial_overlap_gap
            + public_overclaim_gap
            + holdout_overclaim_gap
            + adversarial_overclaim_gap
            + specialist_public_gap
            + specialist_holdout_gap
            + specialist_adversarial_gap
        )
        combined_failures = self._merge_failure_taxonomy(
            [
                public["failure_taxonomy"],
                holdout["failure_taxonomy"],
                adversarial["failure_taxonomy"],
            ]
        )
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
                "adversarial_quality": adversarial_quality,
                "adversarial_pass_rate": adversarial_pass_rate,
                "public_adversarial_quality_delta": adversarial_split_quality_delta,
                "public_overclaim_rate": public_overclaim_rate,
                "holdout_overclaim_rate": holdout_overclaim_rate,
                "adversarial_overclaim_rate": adversarial_overclaim_rate,
                "suite_leakage": leakage,
                "specialist_reference_public_aggregate_delta": float(specialist_reference["aggregate_delta"]),
                "specialist_reference_holdout_aggregate_delta": float(specialist_reference_holdout["aggregate_delta"]),
                "specialist_reference_adversarial_aggregate_delta": float(
                    specialist_reference_adversarial["aggregate_delta"]
                ),
            },
            "gaps": {
                "quality_gap": quality_gap,
                "pass_rate_gap": pass_rate_gap,
                "aggregate_delta_gap": aggregate_delta_gap,
                "case_margin_gap": case_margin_gap,
                "holdout_quality_gap": holdout_quality_gap,
                "split_delta_gap": split_delta_gap,
                "adversarial_quality_gap": adversarial_quality_gap,
                "adversarial_pass_rate_gap": adversarial_pass_rate_gap,
                "adversarial_split_gap": adversarial_split_gap,
                "public_holdout_overlap_gap": public_holdout_overlap_gap,
                "public_adversarial_overlap_gap": public_adversarial_overlap_gap,
                "holdout_adversarial_overlap_gap": holdout_adversarial_overlap_gap,
                "public_overclaim_gap": public_overclaim_gap,
                "holdout_overclaim_gap": holdout_overclaim_gap,
                "adversarial_overclaim_gap": adversarial_overclaim_gap,
                "specialist_public_gap": specialist_public_gap,
                "specialist_holdout_gap": specialist_holdout_gap,
                "specialist_adversarial_gap": specialist_adversarial_gap,
                "per_case_gap": per_case_gap,
                "remaining_distance": remaining_distance,
            },
            "ready": remaining_distance <= 1e-9,
        }

        return {
            "scorecard": scorecard.__dict__,
            "details": details,
            "aggregate_delta": aggregate_delta,
            "benchmark_provenance": self._benchmark_provenance(),
            "holdout_scorecard": holdout["scorecard"].__dict__,
            "holdout_details": holdout["details"],
            "holdout_aggregate_delta": float(holdout["aggregate_delta"]),
            "adversarial_scorecard": adversarial["scorecard"].__dict__,
            "adversarial_details": adversarial["details"],
            "adversarial_aggregate_delta": float(adversarial["aggregate_delta"]),
            "failure_analysis": {
                "public": public["failure_taxonomy"],
                "holdout": holdout["failure_taxonomy"],
                "adversarial": adversarial["failure_taxonomy"],
                "combined": combined_failures,
            },
            "claim_calibration": {
                "public_overclaim_rate": public_overclaim_rate,
                "holdout_overclaim_rate": holdout_overclaim_rate,
                "adversarial_overclaim_rate": adversarial_overclaim_rate,
                "public_overclaim_hits_total": int(public["overclaim_hits_total"]),
                "holdout_overclaim_hits_total": int(holdout["overclaim_hits_total"]),
                "adversarial_overclaim_hits_total": int(adversarial["overclaim_hits_total"]),
            },
            "specialist_reference": {
                "public": {
                    "scorecard": specialist_reference["scorecard"].__dict__,
                    "details": specialist_reference["details"],
                    "aggregate_delta": float(specialist_reference["aggregate_delta"]),
                },
                "holdout": {
                    "scorecard": specialist_reference_holdout["scorecard"].__dict__,
                    "details": specialist_reference_holdout["details"],
                    "aggregate_delta": float(specialist_reference_holdout["aggregate_delta"]),
                },
                "adversarial": {
                    "scorecard": specialist_reference_adversarial["scorecard"].__dict__,
                    "details": specialist_reference_adversarial["details"],
                    "aggregate_delta": float(specialist_reference_adversarial["aggregate_delta"]),
                },
            },
            "benchmark_progress": benchmark_progress,
        }

    def _merge_failure_taxonomy(self, rows: list[dict[str, int]]) -> dict[str, int]:
        merged: dict[str, int] = {}
        for row in rows:
            for key, value in row.items():
                merged[key] = merged.get(key, 0) + int(value)
        return merged
