from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .reality_guard import RealityGuard


@dataclass
class ScalePathProfile:
    key: str
    title: str
    description: str
    strengths: list[str]
    tradeoffs: list[str]
    baseline_monthly_cost_usd: float


class ScalePathDecisionEngine:
    def __init__(self) -> None:
        self.reality_guard = RealityGuard()
        self._profiles = self._default_profiles()

    def evaluate(self, scenario: dict[str, Any]) -> dict[str, Any]:
        scenario_norm = self._normalize_scenario(scenario)
        profile_scores: list[dict[str, Any]] = []
        for profile in self._profiles:
            profile_scores.append(self._score_profile(profile, scenario_norm))
        profile_scores.sort(key=lambda row: float(row["score"]), reverse=True)

        recommended = profile_scores[0] if profile_scores else {}
        alternatives, rejected = self._partition_profiles(profile_scores)
        rationale_text = " ".join(
            [
                str(recommended.get("rationale", "")),
                " ".join(str(item) for item in recommended.get("governance_notes", [])),
            ]
        )
        claim_audit = self.reality_guard.audit_text(rationale_text)

        governance_policy = {
            "data_residency": "local-first" if scenario_norm["privacy_level"] == "strict" else "regional controls",
            "pii_policy": "no raw PII in external escalation payloads",
            "approval_gate": "human approval required for high-risk hybrid escalation",
            "audit_requirement": "persist reproducibility and evidence traces for every decision",
        }

        return {
            "scenario": scenario_norm,
            "recommended_profile": recommended,
            "alternative_profiles": alternatives,
            "rejected_profiles": rejected,
            "governance_policy": governance_policy,
            "claim_calibration": claim_audit,
            "decision_confidence": self._decision_confidence(profile_scores),
        }

    def scenario_analysis(self) -> dict[str, Any]:
        scenarios = [
            {
                "name": "consumer-laptop-research",
                "privacy_level": "strict",
                "monthly_budget_usd": 60.0,
                "latency_sla_ms": 120_000,
                "offline_requirement": True,
                "regulatory_sensitivity": "medium",
                "team_ops_capacity": "small",
                "workload_variability": "medium",
                "peak_task_complexity": "medium",
            },
            {
                "name": "regulated-enterprise-workload",
                "privacy_level": "strict",
                "monthly_budget_usd": 3000.0,
                "latency_sla_ms": 30_000,
                "offline_requirement": False,
                "regulatory_sensitivity": "high",
                "team_ops_capacity": "large",
                "workload_variability": "high",
                "peak_task_complexity": "high",
            },
            {
                "name": "mixed-growth-team",
                "privacy_level": "moderate",
                "monthly_budget_usd": 450.0,
                "latency_sla_ms": 60_000,
                "offline_requirement": False,
                "regulatory_sensitivity": "medium",
                "team_ops_capacity": "medium",
                "workload_variability": "high",
                "peak_task_complexity": "high",
            },
        ]
        results = [self.evaluate(scenario) for scenario in scenarios]
        return {
            "scenarios": results,
            "summary": {
                "scenario_count": len(results),
                "recommended_paths": [result["recommended_profile"]["profile_key"] for result in results],
            },
        }

    def _default_profiles(self) -> list[ScalePathProfile]:
        return [
            ScalePathProfile(
                key="local_only",
                title="Local-Only",
                description="Run all workloads on local small-model infrastructure with no cloud escalation.",
                strengths=[
                    "high privacy control",
                    "offline resilience",
                    "predictable low infrastructure overhead",
                ],
                tradeoffs=[
                    "limited peak capability on very hard tasks",
                    "higher local maintenance burden",
                ],
                baseline_monthly_cost_usd=35.0,
            ),
            ScalePathProfile(
                key="hybrid_escalation",
                title="Hybrid Escalation",
                description="Use local-first execution with policy-gated escalation for hard cases.",
                strengths=[
                    "balances capability and cost",
                    "keeps sensitive data local by default",
                    "scales to harder workloads when needed",
                ],
                tradeoffs=[
                    "requires governance policy enforcement",
                    "more complex routing and observability",
                ],
                baseline_monthly_cost_usd=260.0,
            ),
            ScalePathProfile(
                key="managed_cloud",
                title="Managed Cloud",
                description="Primary execution on managed cloud stack with enterprise controls.",
                strengths=[
                    "high peak capability",
                    "managed operations",
                    "faster scaling with heavy demand",
                ],
                tradeoffs=[
                    "higher recurring cost",
                    "weaker offline resilience",
                    "more stringent data-governance requirements",
                ],
                baseline_monthly_cost_usd=1200.0,
            ),
        ]

    def _normalize_scenario(self, scenario: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(scenario.get("name", "unnamed-scenario")),
            "privacy_level": str(scenario.get("privacy_level", "moderate")).lower(),
            "monthly_budget_usd": float(scenario.get("monthly_budget_usd", 300.0)),
            "latency_sla_ms": int(scenario.get("latency_sla_ms", 60_000)),
            "offline_requirement": bool(scenario.get("offline_requirement", False)),
            "regulatory_sensitivity": str(scenario.get("regulatory_sensitivity", "medium")).lower(),
            "team_ops_capacity": str(scenario.get("team_ops_capacity", "medium")).lower(),
            "workload_variability": str(scenario.get("workload_variability", "medium")).lower(),
            "peak_task_complexity": str(scenario.get("peak_task_complexity", "medium")).lower(),
        }

    def _score_profile(self, profile: ScalePathProfile, scenario: dict[str, Any]) -> dict[str, Any]:
        raw_score = 0.0
        governance_notes: list[str] = []

        if scenario["privacy_level"] == "strict":
            if profile.key == "local_only":
                raw_score += 0.40
            elif profile.key == "hybrid_escalation":
                raw_score += 0.28
                governance_notes.append("Escalation must enforce strict redaction and approval.")
            else:
                raw_score += 0.08
                governance_notes.append("Managed cloud requires strong contractual privacy controls.")
        elif scenario["privacy_level"] == "moderate":
            if profile.key == "hybrid_escalation":
                raw_score += 0.35
            elif profile.key == "managed_cloud":
                raw_score += 0.24
            else:
                raw_score += 0.22
        else:
            if profile.key == "managed_cloud":
                raw_score += 0.34
            elif profile.key == "hybrid_escalation":
                raw_score += 0.30
            else:
                raw_score += 0.16

        budget = float(scenario["monthly_budget_usd"])
        if budget < 120.0:
            raw_score += 0.30 if profile.key == "local_only" else (0.18 if profile.key == "hybrid_escalation" else 0.05)
        elif budget < 700.0:
            raw_score += 0.32 if profile.key == "hybrid_escalation" else (0.20 if profile.key == "local_only" else 0.16)
        else:
            raw_score += 0.33 if profile.key == "managed_cloud" else (0.25 if profile.key == "hybrid_escalation" else 0.18)

        if scenario["offline_requirement"]:
            raw_score += 0.22 if profile.key == "local_only" else (0.10 if profile.key == "hybrid_escalation" else 0.02)
            if profile.key != "local_only":
                governance_notes.append("Add offline fallback for critical workflows.")

        if scenario["peak_task_complexity"] == "high":
            raw_score += 0.20 if profile.key == "hybrid_escalation" else (0.22 if profile.key == "managed_cloud" else 0.08)
        elif scenario["peak_task_complexity"] == "medium":
            raw_score += 0.15 if profile.key == "hybrid_escalation" else (0.12 if profile.key == "local_only" else 0.13)
        else:
            raw_score += 0.16 if profile.key == "local_only" else 0.12

        if scenario["team_ops_capacity"] == "small":
            raw_score += 0.18 if profile.key == "managed_cloud" else (0.15 if profile.key == "hybrid_escalation" else 0.08)
            if profile.key == "local_only":
                governance_notes.append("Local-only path may strain small operations teams.")
        elif scenario["team_ops_capacity"] == "large":
            raw_score += 0.16 if profile.key in {"local_only", "hybrid_escalation"} else 0.14
        else:
            raw_score += 0.14 if profile.key == "hybrid_escalation" else 0.12

        cost_pressure = max(0.0, profile.baseline_monthly_cost_usd - budget) / max(1.0, budget)
        raw_score -= min(0.25, cost_pressure * 0.25)
        normalized_score = max(0.0, min(1.0, raw_score / 1.5))

        rationale = (
            f"{profile.title} selected with weighted fit to privacy={scenario['privacy_level']}, "
            f"budget={scenario['monthly_budget_usd']:.2f}, complexity={scenario['peak_task_complexity']}, "
            "with explicit tradeoff and constraint checks."
        )
        if scenario["regulatory_sensitivity"] == "high" and profile.key != "local_only":
            governance_notes.append("Run compliance review before enabling external model escalation.")
        if scenario["workload_variability"] == "high" and profile.key == "local_only":
            governance_notes.append("High variability may require occasional escalation safety valve.")

        return {
            "profile_key": profile.key,
            "profile_title": profile.title,
            "score": round(normalized_score, 4),
            "raw_score": round(raw_score, 4),
            "description": profile.description,
            "strengths": profile.strengths,
            "tradeoffs": profile.tradeoffs,
            "baseline_monthly_cost_usd": profile.baseline_monthly_cost_usd,
            "governance_notes": governance_notes,
            "rationale": rationale,
        }

    def _decision_confidence(self, scores: list[dict[str, Any]]) -> float:
        if len(scores) < 2:
            return 0.5
        top = float(scores[0]["score"])
        second = float(scores[1]["score"])
        margin = max(0.0, top - second)
        return round(max(0.5, min(0.98, 0.55 + margin)), 4)

    def _partition_profiles(self, profile_scores: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if len(profile_scores) <= 1:
            return [], []
        top = float(profile_scores[0]["score"])
        alternatives: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        alternative_gap_threshold = 0.08
        for candidate in profile_scores[1:]:
            gap = top - float(candidate["score"])
            if gap <= alternative_gap_threshold:
                alternatives.append(candidate)
            else:
                rejected.append(candidate)
        return alternatives, rejected
