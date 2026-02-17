from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Optional


@dataclass
class QECSimulationOutput:
    engine: str
    projected_logical_error_rate: float
    projected_runtime_penalty: float
    confidence: float
    notes: str


@dataclass
class SimulationConsistencyReport:
    passed: bool
    score: float
    hard_failures: list[str]
    soft_failures: list[str]
    normalized_payload: dict[str, float | int]


class QECSimulatorHook:
    """
    QEC simulator integration with graceful fallback.
    - If a simulator backend is available, it can be used.
    - Otherwise, an analytic local proxy is used.
    """

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, float | int]:
        return {
            "baseline_error": float(payload.get("baseline_error", 0.02)),
            "physical_error": float(payload.get("physical_error", 0.01)),
            "rounds": int(payload.get("rounds", 12)),
            "decoder_gain": float(payload.get("decoder_gain", 0.10)),
            "runtime_penalty": float(payload.get("runtime_penalty", 0.12)),
            "max_runtime_penalty": float(payload.get("max_runtime_penalty", 0.15)),
        }

    def _score_report(self, hard_failures: list[str], soft_failures: list[str]) -> float:
        return max(0.0, 1.0 - (0.40 * len(hard_failures)) - (0.10 * len(soft_failures)))

    def _validate_payload(self, payload: dict[str, float | int]) -> SimulationConsistencyReport:
        hard_failures: list[str] = []
        soft_failures: list[str] = []

        baseline_error = float(payload["baseline_error"])
        physical_error = float(payload["physical_error"])
        rounds = int(payload["rounds"])
        decoder_gain = float(payload["decoder_gain"])
        runtime_penalty = float(payload["runtime_penalty"])
        max_runtime_penalty = float(payload["max_runtime_penalty"])

        numeric_fields = {
            "baseline_error": baseline_error,
            "physical_error": physical_error,
            "decoder_gain": decoder_gain,
            "runtime_penalty": runtime_penalty,
            "max_runtime_penalty": max_runtime_penalty,
            "rounds": float(rounds),
        }
        for name, value in numeric_fields.items():
            if not math.isfinite(value):
                hard_failures.append(f"{name} must be finite.")

        if not (0.0 < baseline_error < 1.0):
            hard_failures.append("baseline_error must be in (0, 1).")
        if not (0.0 < physical_error < 1.0):
            hard_failures.append("physical_error must be in (0, 1).")
        if rounds <= 0 or rounds > 500:
            hard_failures.append("rounds must be in [1, 500].")
        if decoder_gain <= -0.5 or decoder_gain >= 0.95:
            hard_failures.append("decoder_gain must be in (-0.5, 0.95).")
        if runtime_penalty < 0.0 or runtime_penalty > 2.0:
            hard_failures.append("runtime_penalty must be in [0, 2].")
        if max_runtime_penalty <= 0.0 or max_runtime_penalty > 2.0:
            hard_failures.append("max_runtime_penalty must be in (0, 2].")

        if runtime_penalty > max_runtime_penalty:
            soft_failures.append("runtime_penalty exceeds configured ceiling.")
        if rounds > 128:
            soft_failures.append("round count is high for laptop-grade execution.")
        if decoder_gain > 0.40:
            soft_failures.append("decoder_gain is aggressive and may overfit idealized regimes.")
        if physical_error > baseline_error * 1.5:
            soft_failures.append("physical_error significantly exceeds baseline_error.")

        return SimulationConsistencyReport(
            passed=not hard_failures,
            score=self._score_report(hard_failures, soft_failures),
            hard_failures=hard_failures,
            soft_failures=soft_failures,
            normalized_payload=payload,
        )

    def _validate_projection(
        self,
        result: QECSimulationOutput,
        payload: dict[str, float | int],
    ) -> tuple[list[str], list[str]]:
        hard_failures: list[str] = []
        soft_failures: list[str] = []

        if not (0.0 < result.projected_logical_error_rate < 1.0):
            hard_failures.append("projected_logical_error_rate must be in (0, 1).")
        if result.projected_runtime_penalty < 0.0 or result.projected_runtime_penalty > 2.0:
            hard_failures.append("projected_runtime_penalty must be in [0, 2].")
        if not (0.0 <= result.confidence <= 1.0):
            soft_failures.append("confidence should be in [0, 1].")
        if result.projected_runtime_penalty > float(payload["max_runtime_penalty"]):
            soft_failures.append("projected runtime penalty exceeds configured ceiling.")
        if result.projected_logical_error_rate >= float(payload["baseline_error"]):
            soft_failures.append("projection does not improve baseline logical error.")
        return hard_failures, soft_failures

    def _format_output(self, result: QECSimulationOutput, report: SimulationConsistencyReport) -> dict[str, Any]:
        if not report.passed:
            status = "rejected"
        elif report.soft_failures:
            status = "accepted-with-warnings"
        else:
            status = "accepted"
        output = result.__dict__.copy()
        output["status"] = status
        output["consistency"] = {
            "passed": report.passed,
            "score": report.score,
            "hard_failures": report.hard_failures,
            "soft_failures": report.soft_failures,
            "normalized_payload": report.normalized_payload,
        }
        return output

    def _rejection_output(self, payload: dict[str, float | int], notes: str) -> QECSimulationOutput:
        return QECSimulationOutput(
            engine="consistency-gate",
            projected_logical_error_rate=max(0.0001, float(payload["baseline_error"])),
            projected_runtime_penalty=max(0.0, float(payload["runtime_penalty"])),
            confidence=0.25,
            notes=notes,
        )

    def _try_external_backend(self, payload: dict[str, Any]) -> Optional[QECSimulationOutput]:
        try:
            import importlib

            # Optional backend hook: users can provide qec_backend.simulate(payload).
            backend = importlib.import_module("qec_backend")
            if hasattr(backend, "simulate"):
                raw = backend.simulate(payload)
                return QECSimulationOutput(
                    engine="external-qec-backend",
                    projected_logical_error_rate=float(raw.get("projected_logical_error_rate", 0.0)),
                    projected_runtime_penalty=float(raw.get("projected_runtime_penalty", 0.0)),
                    confidence=float(raw.get("confidence", 0.7)),
                    notes=str(raw.get("notes", "external backend")),
                )
        except Exception:
            return None
        return None

    def _analytic_proxy(self, payload: dict[str, float | int]) -> QECSimulationOutput:
        baseline_error = float(payload["baseline_error"])
        physical_error = float(payload["physical_error"])
        rounds = int(payload["rounds"])
        decoder_gain = float(payload["decoder_gain"])
        runtime_penalty = float(payload["runtime_penalty"])

        rounds_factor = max(0.80, 1.0 - min(0.25, rounds * 0.005))
        physical_factor = max(0.70, 1.0 - min(0.22, physical_error * 4.0))
        projected = baseline_error * rounds_factor * physical_factor * (1.0 - decoder_gain)
        projected = max(0.0001, projected)
        penalty = runtime_penalty * (1.0 + (rounds * 0.003))
        confidence = max(0.50, 0.88 - abs(physical_error - baseline_error) * 3.0)
        return QECSimulationOutput(
            engine="analytic-proxy",
            projected_logical_error_rate=projected,
            projected_runtime_penalty=penalty,
            confidence=confidence,
            notes="Fallback analytic estimate; replace with calibrated backend for production claims.",
        )

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_payload(payload)
        report = self._validate_payload(normalized)
        if not report.passed:
            rejected = self._rejection_output(normalized, "Rejected by strict consistency gate before simulation.")
            return self._format_output(rejected, report)

        external = self._try_external_backend(normalized)
        if external:
            ext_hard, ext_soft = self._validate_projection(external, normalized)
            if ext_hard:
                report.soft_failures.append("External backend output violated invariants; analytic fallback used.")
                result = self._analytic_proxy(normalized)
            else:
                report.soft_failures.extend(ext_soft)
                result = external
        else:
            result = self._analytic_proxy(normalized)

        hard_failures, soft_failures = self._validate_projection(result, normalized)
        if hard_failures:
            report.hard_failures.extend(hard_failures)
            report.passed = False
            rejected = self._rejection_output(normalized, "Rejected after post-simulation invariant checks.")
            report.score = self._score_report(report.hard_failures, report.soft_failures)
            return self._format_output(rejected, report)

        report.soft_failures.extend(soft_failures)
        report.score = self._score_report(report.hard_failures, report.soft_failures)
        return self._format_output(result, report)
