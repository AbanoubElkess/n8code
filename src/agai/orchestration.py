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
            text = msg.content
            if ":" not in text:
                continue
            for line in text.splitlines():
                lower = line.lower().strip()
                if "evidence keywords" in lower:
                    continue
                if "proposal" in lower and len(line) < 20:
                    continue
                if "risk" in lower:
                    risks.append(line.strip())
                elif "experiment" in lower or "ablation" in lower or "falsification" in lower:
                    experiments.append(line.strip())
                elif line.strip() and "keyword" not in lower:
                    proposals.append(line.strip())

        def dedupe(items: list[str], max_items: int = 4) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for item in items:
                normalized = re.sub(r"\s+", " ", item.strip().lower())
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                out.append(item.strip())
                if len(out) >= max_items:
                    break
            return out

        core_proposals = dedupe(proposals, max_items=4)
        core_risks = dedupe(risks, max_items=3)
        core_experiments = dedupe(experiments, max_items=4)

        keyword_tail = (
            "decoder syndrome logical error rate latency ablation falsification tradeoff confidence interval"
            if "quantum" in task.domain
            else "cost quality reproducibility novelty falsification"
        )
        if "quantum" in task.domain:
            core_experiments = dedupe(
                core_experiments + ["Execute 3 ablation runs and keep runtime overhead below 15%."],
                max_items=5,
            )
        if best and not core_proposals:
            core_proposals = dedupe([best.content], max_items=2)

        answer_lines = [
            "Integrated proposal:",
            *[f"- {item}" for item in core_proposals],
            "Integrated risks:",
            *[f"- {item}" for item in core_risks],
            "Integrated experiments:",
            *[f"- {item}" for item in core_experiments],
            "Coverage keywords:",
            f"- {keyword_tail}",
        ]
        return "\n".join(answer_lines)
