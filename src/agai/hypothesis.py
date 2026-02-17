from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Callable, Optional

from .types import HypothesisProgram


@dataclass
class RuleEvaluation:
    rule: str
    passed: bool
    score: float
    failures: list[str]
    hard_failures: list[str] = field(default_factory=list)
    soft_failures: list[str] = field(default_factory=list)


class FalsificationGate:
    def __init__(self) -> None:
        self._hard_checks: dict[str, Callable[[str], tuple[bool, str]]] = {
            "no-physical-impossibility-claim": self._check_no_perpetual_motion,
            "no-causality-violation-claim": self._check_no_causality_violation,
            "has-testable-prediction": self._check_has_prediction,
            "has-control-parameter": self._check_has_control_parameter,
            "bounded-improvement-claim": self._check_bounded_improvement_claim,
        }
        self._soft_checks: dict[str, Callable[[str], tuple[bool, str]]] = {
            "has-falsification-path": self._check_has_falsification_path,
            "has-baseline-comparator": self._check_has_baseline_comparator,
            "has-uncertainty-quantification": self._check_has_uncertainty_quantification,
        }

    def evaluate_rule(self, rule: str) -> RuleEvaluation:
        hard_failures: list[str] = []
        soft_failures: list[str] = []

        for check_name, check_fn in self._hard_checks.items():
            ok, reason = check_fn(rule)
            if not ok:
                hard_failures.append(f"{check_name}: {reason}")

        for check_name, check_fn in self._soft_checks.items():
            ok, reason = check_fn(rule)
            if not ok:
                soft_failures.append(f"{check_name}: {reason}")

        failures = hard_failures + soft_failures
        passed = not hard_failures
        score = max(0.0, 1.0 - (0.45 * len(hard_failures)) - (0.12 * len(soft_failures)))
        return RuleEvaluation(
            rule=rule,
            passed=passed,
            score=score,
            failures=failures,
            hard_failures=hard_failures,
            soft_failures=soft_failures,
        )

    def _check_no_perpetual_motion(self, rule: str) -> tuple[bool, str]:
        bad_phrases = ("free infinite energy", "zero-loss forever", "perpetual motion")
        lower = rule.lower()
        if any(phrase in lower for phrase in bad_phrases):
            return False, "violates baseline conservation assumptions."
        return True, "ok"

    def _check_no_causality_violation(self, rule: str) -> tuple[bool, str]:
        bad_phrases = (
            "faster than light",
            "instantaneous across any distance",
            "acausal transfer",
            "time reversal signal",
        )
        lower = rule.lower()
        if any(phrase in lower for phrase in bad_phrases):
            return False, "contains causality-violating claim."
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

    def _check_bounded_improvement_claim(self, rule: str) -> tuple[bool, str]:
        percents = [float(match) for match in re.findall(r"(-?\d+(?:\.\d+)?)\s*%", rule)]
        if any(value > 100.0 or value < -100.0 for value in percents):
            return False, "contains out-of-range percentage claims."
        lower = rule.lower()
        if ("zero error" in lower or "perfect fidelity" in lower) and percents:
            return False, "contains unrealistic perfect-performance claim."
        return True, "ok"

    def _check_has_falsification_path(self, rule: str) -> tuple[bool, str]:
        tokens = ("falsification", "ablation", "negative control", "counterexample", "disprove", "refute")
        if any(token in rule.lower() for token in tokens):
            return True, "ok"
        return False, "missing explicit falsification or negative-control path."

    def _check_has_baseline_comparator(self, rule: str) -> tuple[bool, str]:
        tokens = ("baseline", "compared to", "versus", "relative to")
        if any(token in rule.lower() for token in tokens):
            return True, "ok"
        return False, "missing baseline comparison anchor."

    def _check_has_uncertainty_quantification(self, rule: str) -> tuple[bool, str]:
        tokens = ("confidence interval", "variance", "error bar", "uncertainty")
        if any(token in rule.lower() for token in tokens):
            return True, "ok"
        return False, "no explicit uncertainty quantification signal."


class HypothesisExplorer:
    def __init__(self, gate: Optional[FalsificationGate] = None) -> None:
        self.gate = gate or FalsificationGate()

    def propose_counterfactuals(self, seed_program: HypothesisProgram, limit: int = 8) -> list[str]:
        candidates: list[str] = []
        templates = [
            (
                "stress-probe",
                (
                    "Stress probe: if field drive is increased by {value}% versus baseline, perfect fidelity could "
                    "improve by {delta}% with negligible losses."
                ),
            ),
            (
                "coupling-modulation",
                (
                "If coupling is modulated at {value} MHz versus baseline, logical error rate may decrease by {delta}%. "
                "Falsification path: run negative control with fixed syndrome depth and report confidence interval."
                ),
            ),
            (
                "flux-control",
                (
                "Increasing control-field smoothness by {value}% relative to baseline may reduce decoherence bursts by "
                "{delta}%. Validation: ablation on drift compensation plus uncertainty tracking."
                ),
            ),
            (
                "thermal-shift",
                (
                "At temperature shift of {value} mK versus baseline, syndrome stability could increase by {delta}%. "
                "Counterexample search should refute spurious gain under held-out noise."
                ),
            ),
            (
                "stabilizer-scheduling",
                (
                "With stabilizer timing retuned by {value}% compared to baseline, logical error may decrease by {delta}% "
                "under runtime constraint; include ablation and confidence interval checks."
                ),
            ),
        ]
        values = [3, 7, 12, 20, 35]
        deltas = [4, 8, 12, 18, 24]
        risky_deltas = [110, 120, 130, 140, 150]
        for rule in seed_program.rules:
            for family, tmpl in templates:
                active_deltas = risky_deltas if family == "stress-probe" else deltas
                for value, delta in zip(values, active_deltas):
                    candidates.append(f"{tmpl.format(value=value, delta=delta)} Seed constraint: {rule}")
                    if len(candidates) >= limit:
                        return candidates
        return candidates[:limit]

    def rank(self, rules: list[str]) -> list[RuleEvaluation]:
        evals = [self.gate.evaluate_rule(rule) for rule in rules]
        evals.sort(key=lambda row: row.score, reverse=True)
        return evals

    def sandbox(self, seed_program: HypothesisProgram, limit: int = 12, top_k: int = 5) -> dict[str, object]:
        candidates = self.propose_counterfactuals(seed_program=seed_program, limit=limit)
        ranked = self.rank(candidates)
        accepted = [item for item in ranked if item.passed]
        rejected = [item for item in ranked if not item.passed]
        top: list[RuleEvaluation] = accepted[:top_k]
        if len(top) < top_k:
            used = {item.rule for item in top}
            for item in ranked:
                if item.rule in used:
                    continue
                top.append(item)
                used.add(item.rule)
                if len(top) >= top_k:
                    break

        family_coverage: dict[str, int] = {}
        for item in accepted:
            family = self._infer_family(item.rule)
            family_coverage[family] = family_coverage.get(family, 0) + 1

        generated_count = len(ranked)
        accepted_count = len(accepted)
        return {
            "generated_count": generated_count,
            "accepted_count": accepted_count,
            "rejected_count": len(rejected),
            "acceptance_rate": (accepted_count / generated_count) if generated_count else 0.0,
            "family_coverage": family_coverage,
            "top_candidates": [asdict(item) for item in top],
            "rejected_candidates": [asdict(item) for item in rejected],
            "ranked_candidates": [asdict(item) for item in ranked],
        }

    def _infer_family(self, rule: str) -> str:
        lower = rule.lower()
        if "coupling" in lower:
            return "coupling-modulation"
        if "temperature" in lower:
            return "thermal-shift"
        if "flux" in lower or "drift" in lower:
            return "flux-control"
        if "stabilizer" in lower:
            return "stabilizer-scheduling"
        return "general-counterfactual"
