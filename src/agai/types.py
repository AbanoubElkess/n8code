from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol


class MessageIntent(str, Enum):
    PROPOSE = "propose"
    CRITIQUE = "critique"
    PLAN = "plan"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    FINAL = "final"


@dataclass
class CostMeter:
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    energy_joules: float = 0.0
    usd_cost: float = 0.0

    def add(self, other: "CostMeter") -> "CostMeter":
        return CostMeter(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            latency_ms=self.latency_ms + other.latency_ms,
            energy_joules=self.energy_joules + other.energy_joules,
            usd_cost=self.usd_cost + other.usd_cost,
        )


class ModelAdapter(Protocol):
    def generate(self, prompt: str, **kwargs: Any) -> str:
        ...

    def tool_call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def embed(self, text: str) -> list[float]:
        ...

    def score(self, prompt: str, candidate: str) -> float:
        ...

    def cost_meter(self) -> CostMeter:
        ...


@dataclass
class AgentCard:
    id: str
    role: str
    capabilities: list[str]
    budget_limit: dict[str, float]
    safety_policy: dict[str, Any]
    model_profile: dict[str, Any]


@dataclass
class TaskSpec:
    goal: str
    constraints: list[str]
    success_metric: str
    budget: dict[str, float]
    deadline: str
    domain: str


@dataclass
class MessageEnvelope:
    sender: str
    receiver: str
    intent: MessageIntent
    content: str
    evidence_refs: list[str]
    confidence: float
    cost_spent: CostMeter
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class HintPacket:
    hypothesis: str
    counterargument: str
    next_test: str
    expected_failure_mode: str


@dataclass
class EvidenceRecord:
    source: str
    retrieval_time: str
    verifiability: str
    license: str
    hash: str
    notes: str = ""


@dataclass
class HypothesisProgram:
    rules: list[str]
    priors: dict[str, float]
    provenance: list[str] = field(default_factory=list)


@dataclass
class ExperimentPlan:
    simulator: str
    tool_chain: list[str]
    parameters: dict[str, Any]
    stop_criteria: dict[str, Any]
    steps: list[str]


@dataclass
class ResultBundle:
    outcomes: dict[str, Any]
    confidence_intervals: dict[str, tuple[float, float]]
    reproducibility_artifact_ids: list[str]
    contradictions: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)


@dataclass
class EvalCase:
    case_id: str
    prompt: str
    expected: str
    domain: str
    tags: list[str]


@dataclass
class Scorecard:
    quality: float
    latency_ms: float
    cost_usd: float
    energy_joules: float
    reproducibility: float
    novelty: float
    notes: list[str] = field(default_factory=list)

