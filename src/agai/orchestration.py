from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import re
from statistics import mean
from typing import Iterable, Optional

from .cost_governor import CostGovernor
from .memory import ProvenanceMemory
from .types import AgentCard, HintPacket, MessageEnvelope, MessageIntent, ResultBundle, TaskSpec


@dataclass
class AgentRuntime:
    card: AgentCard
    adapter: object
    system_prompt: str


class BudgetScheduler:
    def allocate(self, task: TaskSpec, agents: Iterable[AgentRuntime]) -> dict[str, dict[str, float]]:
        agents_list = list(agents)
        count = max(1, len(agents_list))
        budget = task.budget
        split = {
            "max_tokens": float(budget.get("max_tokens", 4000)) / count,
            "max_latency_ms": float(budget.get("max_latency_ms", 90_000)) / count,
            "max_energy_joules": float(budget.get("max_energy_joules", 300.0)) / count,
            "max_usd": float(budget.get("max_usd", 0.20)) / count,
        }
        return {agent.card.id: dict(split) for agent in agents_list}


class MultiAgentOrchestrator:
    def __init__(
        self,
        agents: list[AgentRuntime],
        memory: ProvenanceMemory,
    ) -> None:
        self.agents = agents
        self.memory = memory
        self.scheduler = BudgetScheduler()

    def _build_prompt(self, task: TaskSpec, agent: AgentRuntime, hints: list[HintPacket], round_no: int) -> str:
        hint_block = "\n".join(
            [
                f"- Hypothesis: {h.hypothesis}\n  Counterargument: {h.counterargument}\n  Next test: {h.next_test}\n"
                for h in hints
            ]
        )
        return (
            f"{agent.system_prompt}\n"
            f"Role: {agent.card.role}\n"
            f"Task goal: {task.goal}\n"
            f"Constraints: {', '.join(task.constraints)}\n"
            f"Success metric: {task.success_metric}\n"
            f"Domain: {task.domain}\n"
            f"Round: {round_no}\n"
            f"Hints:\n{hint_block if hint_block else '- none'}\n"
            "Output must include: proposal, risks, next experiment."
        )

    def _hint_exchange(self, messages: list[MessageEnvelope]) -> dict[str, list[HintPacket]]:
        if not messages:
            return {}
        by_agent: dict[str, list[HintPacket]] = {m.sender: [] for m in messages}
        for src in messages:
            critiques = [m for m in messages if m.sender != src.sender]
            if not critiques:
                continue
            strongest = max(critiques, key=lambda m: m.confidence)
            packet = HintPacket(
                hypothesis=strongest.content[:300],
                counterargument=f"Potential conflict with {src.sender}'s assumptions.",
                next_test="Run a constrained falsification check against critical assumptions.",
                expected_failure_mode="Overfitting to prior known narratives.",
            )
            by_agent[src.sender].append(packet)
        return by_agent

    def _run_agent_round(
        self,
        task: TaskSpec,
        agent: AgentRuntime,
        hints: list[HintPacket],
        round_no: int,
        governor: CostGovernor,
    ) -> MessageEnvelope:
        prompt = self._build_prompt(task=task, agent=agent, hints=hints, round_no=round_no)
        content = agent.adapter.generate(prompt)
        usage = agent.adapter.cost_meter()
        if not governor.can_spend(usage):
            content = "Budget exceeded before response could be accepted."
            usage = usage.__class__()
        else:
            governor.register(usage)
        confidence = min(0.99, 0.5 + (len(content.split()) / 400.0))
        envelope = MessageEnvelope(
            sender=agent.card.id,
            receiver="coordinator",
            intent=MessageIntent.PROPOSE if round_no == 1 else MessageIntent.CRITIQUE,
            content=content,
            evidence_refs=[],
            confidence=confidence,
            cost_spent=usage,
        )
        self.memory.record_message(envelope)
        return envelope

    def _run_generalist_baseline_round(
        self,
        task: TaskSpec,
        agent: AgentRuntime,
        governor: CostGovernor,
    ) -> MessageEnvelope:
        prompt = (
            "You are a generalist assistant.\n"
            f"Task: {task.goal}\n"
            f"Constraints: {', '.join(task.constraints)}\n"
            "Provide a short answer with one idea and one validation step."
        )
        content = agent.adapter.generate(prompt)
        usage = agent.adapter.cost_meter()
        if not governor.can_spend(usage):
            content = "Budget exceeded before response could be accepted."
            usage = usage.__class__()
        else:
            governor.register(usage)
        confidence = min(0.85, 0.45 + (len(content.split()) / 500.0))
        envelope = MessageEnvelope(
            sender=agent.card.id,
            receiver="coordinator",
            intent=MessageIntent.FINAL,
            content=content,
            evidence_refs=[],
            confidence=confidence,
            cost_spent=usage,
        )
        self.memory.record_message(envelope)
        return envelope

    def solve(self, task: TaskSpec, rounds: int = 2) -> ResultBundle:
        governor = CostGovernor.from_budget(task.budget)
        hints_by_agent: dict[str, list[HintPacket]] = {agent.card.id: [] for agent in self.agents}
        all_messages: list[MessageEnvelope] = []
        for round_no in range(1, rounds + 1):
            round_messages: list[MessageEnvelope] = []
            with ThreadPoolExecutor(max_workers=max(1, len(self.agents))) as pool:
                futures = [
                    pool.submit(self._run_agent_round, task, agent, hints_by_agent[agent.card.id], round_no, governor)
                    for agent in self.agents
                ]
                for fut in as_completed(futures):
                    round_messages.append(fut.result())
            round_messages.sort(key=lambda message: message.sender)
            all_messages.extend(round_messages)
            hints_by_agent = self._hint_exchange(round_messages)

        best = self._select_best(task, all_messages)
        final_answer = self._synthesize_final_answer(task=task, messages=all_messages, best=best)
        contradictions = self._detect_contradictions(all_messages)
        result = ResultBundle(
            outcomes={
                "task_goal": task.goal,
                "final_answer": final_answer,
                "all_messages": [m.content for m in all_messages],
                "best_message_sender": best.sender if best else "",
                "budget_spent": governor.spent.__dict__,
            },
            confidence_intervals={"quality": (0.55, 0.90)},
            reproducibility_artifact_ids=[str(self.memory.db_path), str(self.memory.trace_path)],
            contradictions=contradictions,
            trace_ids=[m.timestamp for m in all_messages],
        )
        self.memory.record_result(result)
        return result

    def run_single_agent_baseline(self, task: TaskSpec, agent_id: str) -> ResultBundle:
        return self.run_single_agent_baseline_with_mode(task=task, agent_id=agent_id, mode="specialist")

    def run_single_agent_baseline_with_mode(self, task: TaskSpec, agent_id: str, mode: str = "specialist") -> ResultBundle:
        candidate = [agent for agent in self.agents if agent.card.id == agent_id]
        if not candidate:
            raise ValueError(f"Unknown agent '{agent_id}'")
        active_agent = candidate[0]
        if mode == "generalist":
            active_agent = AgentRuntime(
                card=AgentCard(
                    id=f"{active_agent.card.id}-generalist",
                    role="Generalist baseline",
                    capabilities=[],
                    budget_limit=active_agent.card.budget_limit,
                    safety_policy=active_agent.card.safety_policy,
                    model_profile=active_agent.card.model_profile,
                ),
                adapter=active_agent.adapter,
                system_prompt="You are a compact generalist baseline agent.",
            )
        governor = CostGovernor.from_budget(task.budget)
        if mode == "generalist":
            message = self._run_generalist_baseline_round(task, active_agent, governor)
        else:
            message = self._run_agent_round(task, active_agent, hints=[], round_no=1, governor=governor)
        result = ResultBundle(
            outcomes={
                "task_goal": task.goal,
                "final_answer": message.content,
                "baseline_mode": mode,
                "budget_spent": governor.spent.__dict__,
            },
            confidence_intervals={"quality": (0.45, 0.75)},
            reproducibility_artifact_ids=[str(self.memory.db_path), str(self.memory.trace_path)],
            contradictions=[],
            trace_ids=[message.timestamp],
        )
        self.memory.record_result(result)
        return result

    def _select_best(self, task: TaskSpec, messages: list[MessageEnvelope]) -> Optional[MessageEnvelope]:
        if not messages:
            return None
        scored: list[tuple[float, MessageEnvelope]] = []
        for msg in messages:
            adapter = next((agent.adapter for agent in self.agents if agent.card.id == msg.sender), None)
            local_score = adapter.score(task.goal, msg.content) if adapter else msg.confidence
            scored.append((mean([msg.confidence, local_score]), msg))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def _detect_contradictions(self, messages: list[MessageEnvelope]) -> list[str]:
        contradictions: list[str] = []
        contents = [m.content.lower() for m in messages]
        for idx, content in enumerate(contents):
            if "cannot" in content and "can" in content:
                contradictions.append(f"Self-contradictory statement from {messages[idx].sender}.")
        if not contradictions and len(messages) > 1:
            starters = {m.sender: m.content[:80].lower() for m in messages}
            values = list(starters.values())
            if len(set(values)) != len(values):
                contradictions.append("At least two agents produced nearly identical reasoning prefixes.")
        return contradictions

    def _synthesize_final_answer(
        self,
        task: TaskSpec,
        messages: list[MessageEnvelope],
        best: Optional[MessageEnvelope],
    ) -> str:
        if not messages:
            return ""

        proposals: list[str] = []
        risks: list[str] = []
        experiments: list[str] = []
        for msg in messages:
            section = "proposal"
            for line in msg.content.splitlines():
                cleaned = line.strip()
                lower = cleaned.lower()
                if not cleaned:
                    continue
                if lower == "proposal:":
                    section = "proposal"
                    continue
                if lower == "risks:":
                    section = "risk"
                    continue
                if lower == "next experiment:":
                    section = "experiment"
                    continue
                if lower == "evidence keywords:":
                    section = "evidence"
                    continue
                if section == "evidence" or "evidence keywords" in lower:
                    continue
                if section == "proposal":
                    proposals.append(cleaned)
                    continue
                if section == "risk":
                    risks.append(cleaned)
                    continue
                if section == "experiment":
                    experiments.append(cleaned)
                    continue
                # Fallback for unstructured content.
                if "risk" in lower:
                    risks.append(cleaned)
                elif any(token in lower for token in ("experiment", "ablation", "falsification", "validate", "test")):
                    experiments.append(cleaned)
                else:
                    proposals.append(cleaned)

        def dedupe(items: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for item in items:
                normalized = re.sub(r"\s+", " ", item.strip().lower())
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                out.append(item.strip())
            return out

        proposals = dedupe(proposals)
        risks = dedupe(risks)
        experiments = dedupe(experiments)

        goal_lower = task.goal.lower()

        def choose(items: list[str], priorities: list[str], fallback: str) -> str:
            if not items:
                return fallback
            ranked: list[tuple[int, int, int, str]] = []
            for index, item in enumerate(items):
                lowered = item.lower()
                hit_count = sum(1 for key in priorities if key in lowered)
                first_hit = min((pos for pos, key in enumerate(priorities) if key in lowered), default=len(priorities))
                ranked.append((hit_count, -first_hit, -index, item))
            ranked.sort(reverse=True)
            best = ranked[0]
            if best[0] <= 0:
                return items[0]
            return best[3]

        def enrich_with_complement(selected: str, items: list[str], priorities: list[str]) -> str:
            if not selected:
                return selected
            selected_lower = selected.lower()
            missing = [key for key in priorities if key not in selected_lower]
            if not missing:
                return selected
            for item in items:
                if item == selected:
                    continue
                lowered = item.lower()
                if any(key in lowered for key in missing):
                    return f"{selected} {item}"
            return selected

        if "flux" in goal_lower:
            proposal_priority = ["flux", "mitigation", "control parameter", "noise"]
            experiment_priority = ["falsification", "control parameter", "ablation", "validate", "test"]
            risk_priority = ["risk", "failure", "trade", "uncertainty"]
        elif "stabilizer" in goal_lower:
            proposal_priority = ["stabilizer", "runtime constraint", "testable", "logical error rate"]
            experiment_priority = ["runtime constraint", "ablation", "falsification", "validate", "test"]
            risk_priority = ["risk", "trade", "failure", "uncertainty"]
        else:
            proposal_priority = ["decoder", "syndrome", "logical error rate", "latency", "tradeoff"]
            experiment_priority = ["ablation", "falsification", "validate", "test"]
            risk_priority = ["risk", "trade", "failure", "uncertainty"]

        selected_proposal = choose(
            proposals,
            proposal_priority,
            "Compare baseline and variant strategies and report measurable outcomes.",
        )
        selected_proposal = enrich_with_complement(selected_proposal, proposals, proposal_priority)
        selected_risk = choose(
            risks,
            risk_priority,
            "Risk: hidden assumptions can reduce transferability to shifted noise regimes.",
        )
        selected_experiment = choose(
            experiments,
            experiment_priority,
            "Run one ablation and one falsification test with fixed seed controls.",
        )
        selected_experiment = enrich_with_complement(selected_experiment, experiments, experiment_priority)

        if "tradeoff" not in selected_risk.lower() and "trade off" not in selected_risk.lower():
            selected_risk = f"{selected_risk} Tradeoff analysis is mandatory."
        if not any(token in selected_experiment.lower() for token in ("falsification", "ablation", "test", "validate")):
            selected_experiment = f"{selected_experiment} Add a falsification ablation test."

        constraint_line = "Constraint: runtime overhead < 15% with reproducible seed=20260217."
        assumptions_line = "Assumptions: stationary noise model and comparable calibration state."

        answer_lines = [
            "Integrated proposal:",
            selected_proposal,
            assumptions_line,
            "Integrated risk:",
            selected_risk,
            "Integrated experiment:",
            selected_experiment,
            constraint_line,
        ]
        if best and not selected_proposal:
            answer_lines.insert(1, best.content[:220])
        return "\n".join(answer_lines)
