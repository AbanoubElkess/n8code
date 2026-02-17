from __future__ import annotations

from dataclasses import dataclass

from .types import EvalCase


@dataclass
class QuantumEvalResult:
    case_id: str
    score: float
    passed: bool
    notes: str


def default_quantum_suite() -> list[EvalCase]:
    return [
        EvalCase(
            case_id="QEC-001",
            prompt=(
                "Design a lightweight experiment plan to compare two syndrome decoding strategies "
                "under constrained compute and report expected tradeoffs."
            ),
            expected="decoder tradeoff syndrome error rate latency ablation",
            domain="quantum-error-correction",
            tags=["decoder", "experiment-plan"],
        ),
        EvalCase(
            case_id="QDP-002",
            prompt=(
                "Given rising flux noise, propose a device-level mitigation path and a falsification test "
                "that could disprove your own hypothesis."
            ),
            expected="flux noise mitigation control parameter falsification",
            domain="quantum-device-physics",
            tags=["device-physics", "falsification"],
        ),
        EvalCase(
            case_id="QEC-003",
            prompt=(
                "Suggest a novel but testable modification to a stabilizer cycle that may reduce logical error rate "
                "without increasing runtime by more than 15%."
            ),
            expected="stabilizer logical error rate runtime constraint testable",
            domain="quantum-error-correction",
            tags=["novelty", "constraints"],
        ),
    ]


def score_quantum_answer(expected_hint: str, answer: str) -> float:
    expected = set(expected_hint.lower().split())
    observed = set(answer.lower().split())
    overlap = len(expected & observed)
    coverage = overlap / (len(expected) or 1)
    includes_test = 1.0 if any(token in observed for token in ("test", "ablation", "falsification", "validate")) else 0.0
    includes_risk = 1.0 if any(token in observed for token in ("risk", "failure", "tradeoff")) else 0.0
    score = 0.65 * coverage + 0.20 * includes_test + 0.15 * includes_risk
    return min(1.0, score)


def evaluate_suite_responses(cases: list[EvalCase], answers: dict[str, str], pass_threshold: float = 0.62) -> list[QuantumEvalResult]:
    results: list[QuantumEvalResult] = []
    for case in cases:
        answer = answers.get(case.case_id, "")
        score = score_quantum_answer(case.expected, answer)
        results.append(
            QuantumEvalResult(
                case_id=case.case_id,
                score=score,
                passed=score >= pass_threshold,
                notes="pass" if score >= pass_threshold else "below-threshold",
            )
        )
    return results

