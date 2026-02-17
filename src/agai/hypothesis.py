from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .types import HypothesisProgram


@dataclass
class RuleEvaluation:
    rule: str
    passed: bool
    score: float
    failures: list[str]


class FalsificationGate:
    def __init__(self) -> None:
        self._checks: dict[str, Callable[[str], tuple[bool, str]]] = {
            "no-physical-impossibility-claim": self._check_no_perpetual_motion,
            "has-testable-prediction": self._check_has_prediction,
            "has-control-parameter": self._check_has_control_parameter,
        }

    def evaluate_rule(self, rule: str) -> RuleEvaluation:
        failures: list[str] = []
        for check_name, check_fn in self._checks.items():
            ok, reason = check_fn(rule)
            if not ok:
                failures.append(f"{check_name}: {reason}")
        passed = not failures
        score = max(0.0, 1.0 - (0.3 * len(failures)))
        return RuleEvaluation(rule=rule, passed=passed, score=score, failures=failures)

    def _check_no_perpetual_motion(self, rule: str) -> tuple[bool, str]:
        bad_phrases = ("free infinite energy", "zero-loss forever", "perpetual motion")
        lower = rule.lower()
        if any(phrase in lower for phrase in bad_phrases):
            return False, "violates baseline conservation assumptions."
        return True, "ok"

    def _check_has_prediction(self, rule: str) -> tuple[bool, str]:
        has_numeric = any(char.isdigit() for char in rule)
        has_cmp = any(token in rule for token in (">", "<", "=", "increase", "decrease"))
        if has_numeric or has_cmp:
            return True, "ok"
        return False, "rule lacks measurable prediction."

    def _check_has_control_parameter(self, rule: str) -> tuple[bool, str]:
        keywords = ("temperature", "frequency", "field", "coupling", "voltage", "noise", "error rate")
        if any(word in rule.lower() for word in keywords):
            return True, "ok"
        return False, "no explicit controllable variable found."


class HypothesisExplorer:
    def __init__(self, gate: Optional[FalsificationGate] = None) -> None:
        self.gate = gate or FalsificationGate()

    def propose_counterfactuals(self, seed_program: HypothesisProgram, limit: int = 8) -> list[str]:
        candidates: list[str] = []
        templates = [
            "If coupling is modulated at {value} MHz, effective logical error rate can decrease by {delta}%.",
            "Increasing control-field smoothness by {value}% may reduce decoherence bursts by {delta}%.",
            "At temperature shift of {value} mK, syndrome stability could increase by {delta}%.",
            "Noise anisotropy constrained below {value} leads to decoder gain of {delta}%.",
        ]
        values = [3, 7, 12, 20, 35]
        deltas = [5, 9, 14, 21, 34]
        for rule in seed_program.rules:
            for tmpl in templates:
                for value, delta in zip(values, deltas):
                    candidates.append(f"{tmpl.format(value=value, delta=delta)} Seed constraint: {rule}")
                    if len(candidates) >= limit:
                        return candidates
        return candidates[:limit]

    def rank(self, rules: list[str]) -> list[RuleEvaluation]:
        evals = [self.gate.evaluate_rule(rule) for rule in rules]
        evals.sort(key=lambda row: row.score, reverse=True)
        return evals
