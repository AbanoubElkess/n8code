from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .types import EvalCase


@dataclass
class QuantumEvalResult:
    case_id: str
    score: float
    passed: bool
    notes: str


TOKEN_RE = re.compile(r"[a-zA-Z0-9%+-]+")

CONCEPT_LEXICON: dict[str, set[str]] = {
    "decoder": {"decoder", "decoding", "syndrome", "matching", "belief-propagation", "belief", "propagation"},
    "tradeoff": {"tradeoff", "trade-off", "compromise", "balance", "overhead"},
    "error": {"error", "errors", "logical", "decoherence", "failure", "stability"},
    "runtime": {"runtime", "latency", "overhead", "time", "budget", "constraint", "15%"},
    "falsification": {"falsification", "disprove", "refute", "counterexample", "negative-control", "ablation", "validate", "test"},
    "flux": {"flux", "noise", "mitigation", "field", "frequency", "control", "parameter", "parameters"},
    "stabilizer": {"stabilizer", "cycle", "schedule", "syndrome"},
    "experiment": {"experiment", "ablation", "benchmark", "sweep", "evaluate", "validation"},
    "risk": {"risk", "failure", "tradeoff", "limitation", "uncertainty"},
}


def _strip_evidence_keywords(answer: str) -> str:
    headers = {
        "proposal:",
        "risks:",
        "next experiment:",
        "integrated proposal:",
        "integrated risk:",
        "integrated experiment:",
    }
    keep: list[str] = []
    in_evidence_block = False
    for raw_line in answer.splitlines():
        cleaned = raw_line.strip()
        lower = cleaned.lower()
        if lower in headers:
            in_evidence_block = False
            keep.append(raw_line)
            continue
        if lower == "evidence keywords:":
            in_evidence_block = True
            continue
        if in_evidence_block:
            continue
        keep.append(raw_line)
    return "\n".join(keep)


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _concept_coverage(expected_tokens: set[str], observed_tokens: set[str]) -> float:
    matched = 0
    total = 0
    for concept_tokens in CONCEPT_LEXICON.values():
        if not (concept_tokens & expected_tokens):
            continue
        total += 1
        if concept_tokens & observed_tokens:
            matched += 1
    if total == 0:
        return 0.0
    return matched / total


def _concept_vector(tokens: set[str]) -> list[float]:
    vector: list[float] = []
    for concept_tokens in CONCEPT_LEXICON.values():
        vector.append(1.0 if concept_tokens & tokens else 0.0)
    return vector


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _case_tokens(case: EvalCase) -> set[str]:
    return set(_tokenize(f"{case.prompt} {case.expected}"))


def _cross_split_overlap(left_cases: list[EvalCase], right_cases: list[EvalCase]) -> dict[str, float]:
    if not left_cases or not right_cases:
        return {"mean_best_overlap": 0.0, "max_best_overlap": 0.0}
    scores: list[float] = []
    right_tokens = [_case_tokens(case) for case in right_cases]
    for case in left_cases:
        left_tokens = _case_tokens(case)
        best = max(_jaccard(left_tokens, candidate) for candidate in right_tokens)
        scores.append(best)
    return {
        "mean_best_overlap": sum(scores) / len(scores),
        "max_best_overlap": max(scores),
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(v * v for v in left))
    right_norm = math.sqrt(sum(v * v for v in right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _keyword_stuffing_penalty(expected_tokens: set[str], observed_tokens: list[str]) -> float:
    if not observed_tokens:
        return 0.35
    counts = Counter(observed_tokens)
    total = len(observed_tokens)
    unique_ratio = len(counts) / total
    max_rep_ratio = max(counts.values()) / total
    expected_overuse = sum(max(0, counts.get(token, 0) - 2) for token in expected_tokens) / total

    penalty = 0.0
    penalty += max(0.0, max_rep_ratio - 0.18) * 0.9
    penalty += max(0.0, 0.45 - unique_ratio) * 0.6
    penalty += expected_overuse * 0.7
    return min(0.45, penalty)


def _rubric_signals(tokens: set[str], answer: str) -> dict[str, float]:
    signals = {
        "has_test": 1.0 if CONCEPT_LEXICON["falsification"] & tokens else 0.0,
        "has_risk": 1.0 if CONCEPT_LEXICON["risk"] & tokens else 0.0,
        "has_constraint": 1.0 if CONCEPT_LEXICON["runtime"] & tokens else 0.0,
        "has_quantitative_anchor": 1.0 if any(ch.isdigit() for ch in answer) else 0.0,
    }
    return signals


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


def holdout_quantum_suite() -> list[EvalCase]:
    return [
        EvalCase(
            case_id="QEC-001-H",
            prompt=(
                "Under laptop-scale limits, outline an experiment to compare two syndrome-decoding approaches. "
                "Include expected compromises and a verification route."
            ),
            expected="decoder tradeoff syndrome error rate latency ablation",
            domain="quantum-error-correction",
            tags=["holdout", "decoder", "experiment-plan"],
        ),
        EvalCase(
            case_id="QDP-002-H",
            prompt=(
                "Flux drift is increasing. Propose a device-side mitigation strategy and a concrete falsification "
                "protocol that could invalidate the strategy."
            ),
            expected="flux noise mitigation control parameter falsification",
            domain="quantum-device-physics",
            tags=["holdout", "device-physics", "falsification"],
        ),
        EvalCase(
            case_id="QEC-003-H",
            prompt=(
                "Suggest a testable stabilizer scheduling change aimed at lowering logical error while keeping "
                "runtime overhead constrained below 15%."
            ),
            expected="stabilizer logical error rate runtime constraint testable",
            domain="quantum-error-correction",
            tags=["holdout", "novelty", "constraints"],
        ),
    ]


def adversarial_quantum_suite() -> list[EvalCase]:
    return [
        EvalCase(
            case_id="QEC-004-A",
            prompt=(
                "Design a decoder experiment for correlated syndrome bursts and calibration drift. "
                "Keep runtime overhead below 15%, include explicit tradeoffs, and add a falsification route."
            ),
            expected="decoder syndrome logical error rate runtime tradeoff falsification ablation",
            domain="quantum-error-correction",
            tags=["adversarial", "decoder", "constraints", "falsification"],
        ),
        EvalCase(
            case_id="QDP-005-A",
            prompt=(
                "Flux drift spikes are intermittent and non-stationary. Propose mitigation using control parameters, "
                "then define a disconfirming protocol with negative controls."
            ),
            expected="flux noise mitigation control parameter falsification tradeoff",
            domain="quantum-device-physics",
            tags=["adversarial", "device-physics", "falsification"],
        ),
        EvalCase(
            case_id="QEC-006-A",
            prompt=(
                "Suggest a testable stabilizer scheduling change that targets lower logical error while preserving "
                "strict runtime constraints. Include an ablation-first validation plan."
            ),
            expected="stabilizer logical error rate runtime constraint testable ablation",
            domain="quantum-error-correction",
            tags=["adversarial", "stabilizer", "runtime", "novelty"],
        ),
    ]


def suite_leakage_report() -> dict[str, dict[str, float]]:
    public = default_quantum_suite()
    holdout = holdout_quantum_suite()
    adversarial = adversarial_quantum_suite()
    return {
        "public_vs_holdout": _cross_split_overlap(public, holdout),
        "public_vs_adversarial": _cross_split_overlap(public, adversarial),
        "holdout_vs_adversarial": _cross_split_overlap(holdout, adversarial),
    }


def score_quantum_answer(expected_hint: str, answer: str) -> float:
    expected_tokens = set(_tokenize(expected_hint))
    normalized_answer = _strip_evidence_keywords(answer)
    observed_list = _tokenize(normalized_answer)
    observed_tokens = set(observed_list)

    lexical_coverage = len(expected_tokens & observed_tokens) / (len(expected_tokens) or 1)
    semantic_coverage = _concept_coverage(expected_tokens=expected_tokens, observed_tokens=observed_tokens)
    embedding_similarity = _cosine_similarity(
        _concept_vector(expected_tokens),
        _concept_vector(observed_tokens),
    )

    signals = _rubric_signals(tokens=observed_tokens, answer=normalized_answer)
    base_score = (
        0.30 * lexical_coverage
        + 0.25 * semantic_coverage
        + 0.20 * embedding_similarity
        + 0.10 * signals["has_test"]
        + 0.05 * signals["has_risk"]
        + 0.05 * signals["has_constraint"]
        + 0.05 * signals["has_quantitative_anchor"]
    )
    penalty = _keyword_stuffing_penalty(expected_tokens=expected_tokens, observed_tokens=observed_list)
    return max(0.0, min(1.0, base_score - penalty))


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
