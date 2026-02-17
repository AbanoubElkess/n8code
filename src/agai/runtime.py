from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .adapters import HeuristicSmallModelAdapter, OllamaAdapter
from .alignment import ReflectionDebateLoop
from .baseline_registry import DeclaredBaselineComparator
from .benchmark_tracker import BenchmarkTracker
from .compute_controller import TestTimeComputeController
from .distillation import TraceDistiller
from .evaluation import Evaluator
from .hypothesis import HypothesisExplorer
from .market import MarketGapAnalyzer
from .memory import ProvenanceMemory
from .moonshot_tracker import MoonshotTracker
from .orchestration import AgentRuntime, MultiAgentOrchestrator
from .qec_tools import QECSimulatorHook
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
        self.scale_path = ScalePathDecisionEngine()
        self.explorer = HypothesisExplorer()
        self.guidance = ResearchGuidanceEngine(self.explorer)
        self.compute = TestTimeComputeController()
        self.reflector = ReflectionDebateLoop()
        self.distiller = TraceDistiller()
        self.evaluator = Evaluator()
        self.benchmark_tracker = BenchmarkTracker(history_path=str(self.artifacts_dir / "benchmark_history.jsonl"))
        self.moonshot_tracker = MoonshotTracker(history_path=str(self.artifacts_dir / "moonshot_history.jsonl"))
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
        payload = {
            "compute_decision": compute_decision.__dict__,
            "result": result.__dict__,
            "reflection": reflected.__dict__,
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
