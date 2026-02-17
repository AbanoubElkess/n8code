from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .reality_guard import RealityGuard


@dataclass
class MarketSegment:
    name: str
    description: str
    demand_signal: float


@dataclass
class Competitor:
    name: str
    segment: str
    capability_strength: float
    cost_accessibility: float
    differentiator: str
    gaps: list[str]


@dataclass
class Opportunity:
    key: str
    description: str
    impact: float
    feasibility: float
    defensibility: float
    accessibility: float
    why_now: str
    first_experiment: str

    @property
    def weighted_score(self) -> float:
        return (
            self.impact * 0.35
            + self.feasibility * 0.20
            + self.defensibility * 0.20
            + self.accessibility * 0.25
        )


class MarketGapAnalyzer:
    def __init__(self) -> None:
        self.reality_guard = RealityGuard()

    def taxonomy(self) -> list[MarketSegment]:
        return [
            MarketSegment("infrastructure", "Model serving, vector data, and observability", 0.88),
            MarketSegment("orchestration", "Multi-agent planning, routing, and lifecycle control", 0.93),
            MarketSegment("vertical-copilots", "Domain-specific workflows for legal/health/finance/engineering", 0.90),
            MarketSegment("autonomous-operations", "Agent-based operations, remediation, and task execution", 0.82),
            MarketSegment("science-agents", "Hypothesis generation, experiment planning, and analysis", 0.95),
            MarketSegment("safety-and-eval", "Guardrails, reliability testing, and risk assurance", 0.91),
        ]

    def competitive_map(self) -> list[Competitor]:
        return [
            Competitor(
                name="OpenAI Agents ecosystem",
                segment="orchestration",
                capability_strength=0.92,
                cost_accessibility=0.56,
                differentiator="Strong developer ecosystem and tool use",
                gaps=["local-first parity", "cross-vendor deterministic behavior"],
            ),
            Competitor(
                name="Anthropic MCP ecosystem",
                segment="infrastructure",
                capability_strength=0.86,
                cost_accessibility=0.63,
                differentiator="Interoperable tool interfaces",
                gaps=["full provenance standardization", "budget-native orchestration"],
            ),
            Competitor(
                name="Cloud hyperscaler agent stacks",
                segment="autonomous-operations",
                capability_strength=0.90,
                cost_accessibility=0.42,
                differentiator="Managed services and enterprise integration",
                gaps=["consumer affordability", "offline resilience"],
            ),
            Competitor(
                name="Frontier science copilots",
                segment="science-agents",
                capability_strength=0.89,
                cost_accessibility=0.35,
                differentiator="Deep lab-domain integration",
                gaps=["reproducibility-by-default", "counterfactual hypothesis controls"],
            ),
            Competitor(
                name="Open-source local agent frameworks",
                segment="orchestration",
                capability_strength=0.74,
                cost_accessibility=0.92,
                differentiator="Low cost and modifiability",
                gaps=["benchmark rigor", "scientific falsification workflows"],
            ),
        ]

    def missing_piece_opportunities(self) -> list[Opportunity]:
        entries = [
            Opportunity(
                key="cost-native-orchestration",
                description="Quality-per-dollar/watt optimized planner as first-class objective",
                impact=0.97,
                feasibility=0.83,
                defensibility=0.85,
                accessibility=0.95,
                why_now="Agent adoption is constrained by economics outside enterprise budgets.",
                first_experiment="Implement adaptive branch-prune orchestration and compare cost-normalized score.",
            ),
            Opportunity(
                key="model-independent-behavior",
                description="Stable behavior layer across local and cloud model backends",
                impact=0.92,
                feasibility=0.78,
                defensibility=0.83,
                accessibility=0.93,
                why_now="Teams increasingly need hybrid or migration-ready architecture.",
                first_experiment="Run identical task bundles on 3 adapters and quantify divergence.",
            ),
            Opportunity(
                key="trust-and-provenance-fabric",
                description="Inter-agent evidence lineage and confidence calibration standard",
                impact=0.91,
                feasibility=0.74,
                defensibility=0.88,
                accessibility=0.86,
                why_now="Multi-agent systems fail silently without traceable provenance.",
                first_experiment="Enforce per-message evidence hashes and contradiction surfacing.",
            ),
            Opportunity(
                key="science-workflow-auditability",
                description="Reproducible autonomous science workflows with falsification gates",
                impact=0.96,
                feasibility=0.69,
                defensibility=0.89,
                accessibility=0.78,
                why_now="Scientific trust requires repeatability and explicit error bars.",
                first_experiment="Replay experiment-plan generations across seeded perturbations.",
            ),
            Opportunity(
                key="counterfactual-physics-lab",
                description="Hypothesis generator that explores nonstandard rules with hard constraints",
                impact=0.90,
                feasibility=0.61,
                defensibility=0.92,
                accessibility=0.72,
                why_now="Novel scientific jumps need controlled speculative exploration.",
                first_experiment="Generate and falsify 100 counterfactual rules against invariant checks.",
            ),
            Opportunity(
                key="researcher-guidance-dag",
                description="Natural-language to executable experiment DAG conversion",
                impact=0.94,
                feasibility=0.81,
                defensibility=0.86,
                accessibility=0.91,
                why_now="Most users need structured guidance, not raw model output.",
                first_experiment="Map user question to simulator-ready plan with milestones.",
            ),
            Opportunity(
                key="contradiction-preserving-memory",
                description="Memory that stores disagreement and uncertainty rather than flattening it",
                impact=0.88,
                feasibility=0.76,
                defensibility=0.81,
                accessibility=0.84,
                why_now="Consensus-only memory hides scientific edge cases.",
                first_experiment="Track contradiction density and measure downstream correction gain.",
            ),
            Opportunity(
                key="secure-toolchain-runtime",
                description="Prompt-injection-resistant tool execution policies",
                impact=0.93,
                feasibility=0.80,
                defensibility=0.79,
                accessibility=0.87,
                why_now="Tool-using agents increasingly face indirect prompt attacks.",
                first_experiment="Inject malicious payloads and report blocked execution rate.",
            ),
            Opportunity(
                key="discovery-eval-harness",
                description="Evaluation framework for open-ended discovery tasks",
                impact=0.89,
                feasibility=0.71,
                defensibility=0.82,
                accessibility=0.79,
                why_now="Static QA benchmarks miss real discovery performance.",
                first_experiment="Create novelty + reproducibility scorecard with blind review prompts.",
            ),
            Opportunity(
                key="laptop-grade-research-stack",
                description="Consumer-hardware research agent stack for broad public access",
                impact=0.95,
                feasibility=0.77,
                defensibility=0.80,
                accessibility=0.98,
                why_now="Large portions of users are excluded by hardware and subscription costs.",
                first_experiment="Run end-to-end workflow on a single laptop budget envelope.",
            ),
        ]
        entries.sort(key=lambda row: row.weighted_score, reverse=True)
        return entries

    def report(self) -> dict[str, Any]:
        taxonomy = self.taxonomy()
        competitors = self.competitive_map()
        opportunities = self.missing_piece_opportunities()
        opportunity_rows: list[dict[str, Any]] = []
        for row in opportunities:
            payload = {**asdict(row), "weighted_score": row.weighted_score}
            payload["maturity_band"] = self.reality_guard.maturity_band(
                feasibility=row.feasibility,
                accessibility=row.accessibility,
            )
            audit = self.reality_guard.audit_text(
                f"{row.description} {row.why_now} {row.first_experiment}"
            )
            payload["naming_risk_level"] = audit["risk_level"]
            payload["naming_overclaim_hits"] = audit["overclaim_hits"]
            payload["naming_reality_score"] = audit["reality_score"]
            opportunity_rows.append(payload)

        naming_reality = self.reality_guard.audit_market_opportunities(opportunity_rows)
        return {
            "taxonomy": [asdict(row) for row in taxonomy],
            "competitive_map": [asdict(row) for row in competitors],
            "opportunities": opportunity_rows,
            "naming_reality": naming_reality,
        }
