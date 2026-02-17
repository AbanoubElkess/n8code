from __future__ import annotations

import math
import time
from collections import Counter
from typing import Any

from .types import CostMeter


class BaseModelAdapter:
    """
    Base helper for lightweight adapters.
    Provides deterministic lexical scoring and cost accounting helpers.
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._last_cost = CostMeter()

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def _start_timer(self) -> float:
        return time.perf_counter()

    def _finalize_cost(self, prompt: str, output: str, start: float, usd_per_1k: float = 0.0) -> None:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        tokens_in = self._estimate_tokens(prompt)
        tokens_out = self._estimate_tokens(output)
        token_total = tokens_in + tokens_out
        self._last_cost = CostMeter(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=elapsed_ms,
            energy_joules=token_total * 0.0017,
            usd_cost=(token_total / 1000.0) * usd_per_1k,
        )

    def score(self, prompt: str, candidate: str) -> float:
        """
        Cheap model-agnostic scorer:
        weighted lexical overlap + brevity penalty to avoid empty/highly short answers.
        """
        p_tokens = Counter(prompt.lower().split())
        c_tokens = Counter(candidate.lower().split())
        overlap = sum((p_tokens & c_tokens).values())
        c_size = sum(c_tokens.values()) or 1
        precision = overlap / c_size
        coverage = overlap / (sum(p_tokens.values()) or 1)
        length_penalty = 1.0 - math.exp(-c_size / 12.0)
        return float((0.55 * precision + 0.45 * coverage) * length_penalty)

    def cost_meter(self) -> CostMeter:
        return self._last_cost

    def tool_call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "tool": tool_name,
            "payload": payload,
            "status": "unsupported",
            "message": f"Adapter '{self.model_name}' has no native tool execution.",
        }

