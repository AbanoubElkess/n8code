from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .adapters import HeuristicSmallModelAdapter, OllamaAdapter
from .alignment import ReflectionDebateLoop
from .baseline_attestation import ExternalBaselineAttestationService
from .baseline_ingestion import ExternalBaselineIngestionService
from .baseline_registry import DeclaredBaselineComparator
from .benchmark_tracker import BenchmarkTracker
from .compute_controller import TestTimeComputeController
from .direction_tracker import DirectionTracker
from .distillation import TraceDistiller
from .evaluation import Evaluator
from .hypothesis import HypothesisExplorer
from .market import MarketGapAnalyzer
from .memory import ProvenanceMemory
from .moonshot_tracker import MoonshotTracker
from .orchestration import AgentRuntime, MultiAgentOrchestrator
from .qec_tools import QECSimulatorHook
from .reality_guard import RealityGuard
from .release_status import ReleaseStatusEvaluator
from .scale_path import ScalePathDecisionEngine
from .research_guidance import ResearchGuidanceEngine
from .tool_registry import MCPToolRegistry, ToolSpec
from .tool_reasoning import ToolReasoningEngine
from .types import AgentCard, EvidenceRecord, TaskSpec


class AgenticRuntime:
    def __init__(
        self,
        use_ollama: bool = False,
        ollama_model: str = "llama3.2:3b",
        artifacts_dir: str = "artifacts",
    ) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.memory = ProvenanceMemory(
            db_path=str(self.artifacts_dir / "agai.sqlite"),
            trace_path=str(self.artifacts_dir / "trace.jsonl"),
        )
        self.tool_registry = MCPToolRegistry()
        self.qec_hook = QECSimulatorHook()
        self._register_default_tools()
        self.market = MarketGapAnalyzer()
        self.reality_guard = RealityGuard()
        self.scale_path = ScalePathDecisionEngine()
        self.release_status = ReleaseStatusEvaluator()
        self.explorer = HypothesisExplorer()
        self.guidance = ResearchGuidanceEngine(self.explorer)
        self.compute = TestTimeComputeController()
        self.reflector = ReflectionDebateLoop()
        self.distiller = TraceDistiller()
        self.evaluator = Evaluator()
        self.benchmark_tracker = BenchmarkTracker(history_path=str(self.artifacts_dir / "benchmark_history.jsonl"))
        self.moonshot_tracker = MoonshotTracker(history_path=str(self.artifacts_dir / "moonshot_history.jsonl"))
        self.direction_tracker = DirectionTracker(history_path=str(self.artifacts_dir / "direction_history.jsonl"))
        self.declared_baseline_comparator = DeclaredBaselineComparator()
        self.tool_engine = ToolReasoningEngine(self.tool_registry)
        self.agents = self._build_agents(use_ollama=use_ollama, ollama_model=ollama_model)
        self.orchestrator = MultiAgentOrchestrator(agents=self.agents, memory=self.memory)

    def _build_agents(self, use_ollama: bool, ollama_model: str) -> list[AgentRuntime]:
        def adapter() -> object:
            if use_ollama:
                return OllamaAdapter(model_name=ollama_model)
            return HeuristicSmallModelAdapter()

        cards = [
            AgentCard(
                id="planner",
                role="Research planner",
                capabilities=["decompose", "plan", "prioritize"],
                budget_limit={"max_tokens": 1400, "max_usd": 0.03},
                safety_policy={"allow_speculation": True, "require_falsification": True},
                model_profile={"size": "small", "provider": "local"},
            ),
            AgentCard(
                id="critic",
                role="Falsification critic",
                capabilities=["critique", "counterexample", "risk-analysis"],
                budget_limit={"max_tokens": 1200, "max_usd": 0.03},
                safety_policy={"allow_speculation": False, "require_evidence": True},
                model_profile={"size": "small", "provider": "local"},
            ),
            AgentCard(
                id="physicist",
                role="Quantum device reasoning specialist",
                capabilities=["qec", "device-physics", "experiment-design"],
                budget_limit={"max_tokens": 1500, "max_usd": 0.04},
                safety_policy={"require_constraints": True},
                model_profile={"size": "small", "provider": "local"},
            ),
        ]
        prompts = {
            "planner": "You are a concise scientific planner optimizing quality under strict compute cost.",
            "critic": "You aggressively search for failure modes and hidden assumptions.",
            "physicist": "You focus on quantum error correction and testable device-level interventions.",
        }
        return [AgentRuntime(card=card, adapter=adapter(), system_prompt=prompts[card.id]) for card in cards]

    def _register_default_tools(self) -> None:
        self.tool_registry.register(
            ToolSpec(
                name="budget_estimator",
                description="Estimate cost envelope for a run plan.",
                input_schema={"required": ["num_agents", "avg_tokens_per_agent"]},
            ),
            lambda payload: {
                "estimated_tokens": payload["num_agents"] * payload["avg_tokens_per_agent"],
                "estimated_usd": round(payload["num_agents"] * payload["avg_tokens_per_agent"] * 0.0000002, 6),
            },
        )
        self.tool_registry.register(
            ToolSpec(
                name="syndrome_tradeoff_estimator",
                description="Toy estimator for QEC tradeoffs in constrained runs.",
                input_schema={"required": ["baseline_error", "runtime_penalty"]},
            ),
            lambda payload: {
                "projected_error": max(0.0001, float(payload["baseline_error"]) * (1.0 - 0.08)),
                "projected_runtime_penalty": float(payload["runtime_penalty"]) * 1.05,
            },
        )
        self.tool_registry.register(
            ToolSpec(
                name="qec_simulator_hook",
                description=(
                    "QEC simulator hook for decoder/device studies. "
                    "Uses external backend if available, otherwise analytic fallback."
                ),
                input_schema={"required": ["baseline_error", "physical_error", "rounds"]},
            ),
            lambda payload: self.qec_hook.run(payload),
        )

    def generate_market_gap_report(self) -> dict[str, Any]:
        report = self.market.report()
        payload = json.dumps(report, sort_keys=True).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        evidence = EvidenceRecord(
            source="internal-market-analysis-engine",
            retrieval_time=datetime.utcnow().isoformat(),
            verifiability="deterministic-inputs",
            license="internal",
            hash=digest,
            notes="Generated from embedded taxonomy and opportunity matrix logic.",
        )
        self.memory.record_evidence(evidence)
        out_path = self.artifacts_dir / "market_gap_report.json"
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
        return report

    def _load_or_run_eval_report(self) -> tuple[dict[str, Any], str]:
        eval_path = self.artifacts_dir / "quantum_hard_suite_eval.json"
        if eval_path.exists():
            return json.loads(eval_path.read_text(encoding="utf-8")), "cached-artifact"
        return self.run_quantum_hard_suite(), "fresh-evaluation"

    def _load_or_generate_market_report(self) -> tuple[dict[str, Any], str]:
        report_path = self.artifacts_dir / "market_gap_report.json"
        if report_path.exists():
            return json.loads(report_path.read_text(encoding="utf-8")), "cached-artifact"
        return self.generate_market_gap_report(), "fresh-generation"

    def _load_direction_policy(self) -> dict[str, float | int]:
        default_policy: dict[str, float | int] = {
            "min_combined_average_reality_score": 0.90,
            "max_market_high_risk_opportunities": 0,
            "max_market_medium_risk_opportunities": 2,
        }
        policy_path = Path("config/repro_policy.json")
        if not policy_path.exists():
            return default_policy
        try:
            payload = json.loads(policy_path.read_text(encoding="utf-8"))
            gates = payload.get("direction_gates", {})
            return {
                "min_combined_average_reality_score": float(
                    gates.get(
                        "min_combined_average_reality_score",
                        default_policy["min_combined_average_reality_score"],
                    )
                ),
                "max_market_high_risk_opportunities": int(
                    gates.get(
                        "max_market_high_risk_opportunities",
                        default_policy["max_market_high_risk_opportunities"],
                    )
                ),
                "max_market_medium_risk_opportunities": int(
                    gates.get(
                        "max_market_medium_risk_opportunities",
                        default_policy["max_market_medium_risk_opportunities"],
                    )
                ),
            }
        except Exception:  # noqa: BLE001
            return default_policy

    def run_quantum_research_demo(self, question: str) -> dict[str, Any]:
        task = TaskSpec(
            goal=question,
            constraints=[
                "single-consumer-laptop",
                "small-model-only",
                "must include falsification path",
                "budget-first optimization",
            ],
            success_metric="hard-suite-measurable-improvement",
            budget={"max_tokens": 3600, "max_latency_ms": 80_000, "max_energy_joules": 240.0, "max_usd": 0.12},
            deadline="same-session",
            domain="quantum-error-correction-and-device-physics",
        )
        compute_decision = self.compute.decide(uncertainty=0.72, budget_ratio_remaining=0.85, recent_gain=0.06)
        result = self.orchestrator.solve(task=task, rounds=max(2, compute_decision.depth))
        reflected = self.reflector.run(str(result.outcomes.get("final_answer", "")))
        cost_estimate = self.tool_engine.run(
            tool_name="budget_estimator",
            payload={"num_agents": len(self.agents), "avg_tokens_per_agent": 800},
        )
        syndrome_estimate = self.tool_engine.run(
            tool_name="syndrome_tradeoff_estimator",
            payload={"baseline_error": 0.018, "runtime_penalty": 0.12},
        )
        qec_simulation = self.tool_engine.run(
            tool_name="qec_simulator_hook",
            payload={
                "baseline_error": 0.018,
                "physical_error": 0.011,
                "rounds": 15,
                "decoder_gain": 0.13,
                "runtime_penalty": 0.10,
            },
        )
        experiment_plan, hypotheses = self.guidance.build_experiment_plan(
            question=question,
            domain=task.domain,
            constraints=task.constraints,
            budget=task.budget,
        )
        sandbox_report = self.guidance.latest_sandbox_report()
        execution_dag = self.guidance.latest_execution_dag()
        execution_validation = self.guidance.latest_execution_validation()
        final_answer = str(result.outcomes.get("final_answer", ""))
        revised_answer = str(reflected.revised_answer)
        final_claim_audit = self.reality_guard.audit_text(final_answer)
        revised_claim_audit = self.reality_guard.audit_text(revised_answer)
        reality_score_delta = float(revised_claim_audit.get("reality_score", 0.0)) - float(
            final_claim_audit.get("reality_score", 0.0)
        )
        if reality_score_delta > 1e-9:
            calibration_direction = "improved"
        elif reality_score_delta < -1e-9:
            calibration_direction = "regressed"
        else:
            calibration_direction = "unchanged"
        payload = {
            "compute_decision": compute_decision.__dict__,
            "result": result.__dict__,
            "reflection": reflected.__dict__,
            "claim_calibration": {
                "final_answer": final_claim_audit,
                "revised_answer": revised_claim_audit,
                "reality_score_delta": round(reality_score_delta, 6),
                "direction": calibration_direction,
            },
            "tool_reasoning": {
                "budget_estimator": cost_estimate.__dict__,
                "syndrome_tradeoff_estimator": syndrome_estimate.__dict__,
                "qec_simulator_hook": qec_simulation.__dict__,
            },
            "experiment_plan": experiment_plan.__dict__,
            "hypothesis_candidates": hypotheses,
            "hypothesis_sandbox": sandbox_report,
            "researcher_guidance": {
                "execution_dag": execution_dag,
                "execution_validation": execution_validation,
                "next_action": execution_dag.get("entry_node", ""),
            },
        }
        out_path = self.artifacts_dir / "quantum_demo_output.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return payload

    def run_quantum_hard_suite(self) -> dict[str, Any]:
        eval_report = self.evaluator.evaluate_quantum_suite(
            orchestrator=self.orchestrator,
            baseline_agent_id="planner",
        )
        eval_report["declared_baseline_comparison"] = self.declared_baseline_comparator.compare(eval_report)
        snapshot = self.benchmark_tracker.record(eval_report)
        eval_report["benchmark_tracking"] = {
            "snapshot": snapshot,
            "summary": self.benchmark_tracker.summary(),
        }
        moonshot_snapshot = self.moonshot_tracker.record(eval_report)
        eval_report["moonshot_tracking"] = {
            "snapshot": moonshot_snapshot,
            "summary": self.moonshot_tracker.summary(),
        }
        out_path = self.artifacts_dir / "quantum_hard_suite_eval.json"
        out_path.write_text(json.dumps(eval_report, indent=2, ensure_ascii=True), encoding="utf-8")
        return eval_report

    def run_release_status(self) -> dict[str, Any]:
        eval_report, source = self._load_or_run_eval_report()
        payload = self.release_status.evaluate(eval_report)
        payload["input_source"] = source
        out_path = self.artifacts_dir / "release_status.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return payload

    def run_direction_status(self) -> dict[str, Any]:
        eval_report, eval_source = self._load_or_run_eval_report()
        market_report, market_source = self._load_or_generate_market_report()
        direction_policy = self._load_direction_policy()
        release_status = self.release_status.evaluate(eval_report)
        benchmark_progress = eval_report.get("benchmark_progress", {})
        benchmark_gaps = benchmark_progress.get("gaps", {})
        claim_calibration = eval_report.get("claim_calibration", {})
        external_gate = release_status.get("gates", {}).get("external_claim_gate", {})
        market_naming = market_report.get("naming_reality", {})
        market_risk_counts = market_naming.get("risk_counts", {})

        internal_remaining_distance = float(benchmark_gaps.get("remaining_distance", 0.0))
        external_claim_distance = int(external_gate.get("external_claim_distance", 0))
        public_overclaim_rate = float(claim_calibration.get("public_overclaim_rate", 0.0))
        max_public_overclaim_rate = float(
            benchmark_progress.get("targets", {}).get("max_public_overclaim_rate", 0.0)
        )
        overclaim_rate_gap = max(0.0, public_overclaim_rate - max_public_overclaim_rate)
        combined_average_reality_score = float(claim_calibration.get("combined_average_reality_score", 0.0))
        market_high_risk = int(market_risk_counts.get("high", 0))
        market_medium_risk = int(market_risk_counts.get("medium", 0))
        min_combined_reality = float(direction_policy["min_combined_average_reality_score"])
        max_high_risk = int(direction_policy["max_market_high_risk_opportunities"])
        max_medium_risk = int(direction_policy["max_market_medium_risk_opportunities"])
        naming_reality_gate_pass = (
            combined_average_reality_score >= min_combined_reality
            and market_high_risk <= max_high_risk
            and market_medium_risk <= max_medium_risk
        )

        next_priority = "maintain calibration and continue external replication coverage"
        if internal_remaining_distance > 1e-9:
            next_priority = "close internal benchmark remaining_distance before new claim scope changes"
        elif not naming_reality_gate_pass:
            next_priority = "reduce naming-risk and raise combined reality score before broadening claim language"
        elif external_claim_distance > 0:
            next_priority = "ingest and attest additional external baselines to reduce external_claim_distance"
        elif overclaim_rate_gap > 1e-9:
            next_priority = "reduce overclaim rate to stay below benchmark target"

        payload: dict[str, Any] = {
            "status": "ok",
            "sources": {
                "eval": eval_source,
                "market": market_source,
            },
            "distance": {
                "internal_remaining_distance": internal_remaining_distance,
                "external_claim_distance": external_claim_distance,
                "public_overclaim_rate_gap": overclaim_rate_gap,
            },
            "direction": {
                "internal_ready": bool(benchmark_progress.get("ready", False)),
                "external_claim_ready": bool(release_status.get("external_claim_ready", False)),
                "claim_scope": str(release_status.get("claim_scope", "unknown")),
                "combined_average_reality_score": combined_average_reality_score,
                "market_high_risk_opportunities": market_high_risk,
                "market_medium_risk_opportunities": market_medium_risk,
            },
            "gates": {
                "naming_reality_gate": {
                    "pass": naming_reality_gate_pass,
                    "reason": (
                        "naming and calibration thresholds satisfied"
                        if naming_reality_gate_pass
                        else "naming and calibration thresholds not satisfied"
                    ),
                    "combined_average_reality_score": combined_average_reality_score,
                    "min_combined_average_reality_score": min_combined_reality,
                    "market_high_risk_opportunities": market_high_risk,
                    "max_market_high_risk_opportunities": max_high_risk,
                    "market_medium_risk_opportunities": market_medium_risk,
                    "max_market_medium_risk_opportunities": max_medium_risk,
                }
            },
            "blockers": {
                "external_claim_blockers": external_gate.get("blockers", {}),
            },
            "policy": {
                "direction_gates": direction_policy,
            },
            "next_priority": next_priority,
            "disclaimer": (
                "Direction status is internal calibration telemetry and does not imply external leaderboard parity."
            ),
        }
        tracking_snapshot = self.direction_tracker.record(payload)
        payload["tracking"] = {
            "snapshot": tracking_snapshot,
            "summary": self.direction_tracker.summary(),
        }
        out_path = self.artifacts_dir / "direction_status.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return payload

    def run_ingest_external_baseline(self, input_path: str, registry_path: str | None = None) -> dict[str, Any]:
        service = ExternalBaselineIngestionService(
            registry_path=registry_path or "config/frontier_baselines.json"
        )
        payload = service.ingest_file(input_path=input_path)
        out_path = self.artifacts_dir / "baseline_ingest_result.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return payload

    def run_attest_external_baseline(
        self,
        baseline_id: str,
        registry_path: str | None = None,
        max_metric_delta: float = 0.02,
        eval_path: str | None = None,
    ) -> dict[str, Any]:
        if eval_path:
            path = Path(eval_path)
            if not path.exists():
                return {
                    "status": "error",
                    "reason": f"eval artifact not found: {path}",
                    "baseline_id": baseline_id,
                }
            eval_report = json.loads(path.read_text(encoding="utf-8"))
            source = "explicit-eval-artifact"
        else:
            path = self.artifacts_dir / "quantum_hard_suite_eval.json"
            if path.exists():
                eval_report = json.loads(path.read_text(encoding="utf-8"))
                source = "cached-eval-artifact"
            else:
                eval_report = self.run_quantum_hard_suite()
                source = "fresh-evaluation"
        service = ExternalBaselineAttestationService(
            registry_path=registry_path or "config/frontier_baselines.json"
        )
        payload = service.attest_from_eval_report(
            baseline_id=baseline_id,
            eval_report=eval_report,
            max_metric_delta=max_metric_delta,
        )
        payload["input_source"] = source
        out_path = self.artifacts_dir / "baseline_attest_result.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return payload

    def run_trace_distillation(self) -> dict[str, Any]:
        distilled = self.distiller.distill(
            trace_path=str(self.artifacts_dir / "trace.jsonl"),
            output_path=str(self.artifacts_dir / "distilled_policy.json"),
        )
        return distilled

    def run_scale_path_decision_framework(self) -> dict[str, Any]:
        default_scenario = {
            "name": "default-local-first",
            "privacy_level": "strict",
            "monthly_budget_usd": 250.0,
            "latency_sla_ms": 60_000,
            "offline_requirement": True,
            "regulatory_sensitivity": "medium",
            "team_ops_capacity": "medium",
            "workload_variability": "high",
            "peak_task_complexity": "high",
        }
        decision = self.scale_path.evaluate(default_scenario)
        scenario_analysis = self.scale_path.scenario_analysis()
        payload = {
            "default_decision": decision,
            "scenario_analysis": scenario_analysis,
        }
        out_path = self.artifacts_dir / "scale_path_decision.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return payload
