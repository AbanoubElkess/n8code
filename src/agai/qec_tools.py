from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class QECSimulationOutput:
    engine: str
    projected_logical_error_rate: float
    projected_runtime_penalty: float
    confidence: float
    notes: str


class QECSimulatorHook:
    """
    QEC simulator integration with graceful fallback.
    - If a simulator backend is available, it can be used.
    - Otherwise, an analytic local proxy is used.
    """

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

    def _analytic_proxy(self, payload: dict[str, Any]) -> QECSimulationOutput:
        baseline_error = float(payload.get("baseline_error", 0.02))
        physical_error = float(payload.get("physical_error", 0.01))
        rounds = int(payload.get("rounds", 12))
        decoder_gain = float(payload.get("decoder_gain", 0.10))
        runtime_penalty = float(payload.get("runtime_penalty", 0.12))

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
        external = self._try_external_backend(payload)
        result = external or self._analytic_proxy(payload)
        return result.__dict__
