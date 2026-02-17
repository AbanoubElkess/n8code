from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..model_adapter import BaseModelAdapter


class OllamaAdapter(BaseModelAdapter):
    def __init__(self, model_name: str = "llama3.2:3b", endpoint: str = "http://localhost:11434") -> None:
        super().__init__(model_name=model_name)
        self.endpoint = endpoint.rstrip("/")

    def _post_json(self, path: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)

    def generate(self, prompt: str, **kwargs: Any) -> str:
        start = self._start_timer()
        payload = {
            "model": kwargs.get("model", self.model_name),
            "prompt": prompt,
            "stream": False,
            "options": kwargs.get("options", {}),
        }
        try:
            raw = self._post_json("/api/generate", payload=payload)
            output = str(raw.get("response", "")).strip()
            if not output:
                output = "No model response generated."
        except urllib.error.URLError as exc:
            output = f"[ollama-unavailable] {exc}"
        self._finalize_cost(prompt=prompt, output=output, start=start, usd_per_1k=0.0002)
        return output

    def embed(self, text: str) -> list[float]:
        try:
            raw = self._post_json("/api/embed", payload={"model": self.model_name, "input": text})
            embeddings = raw.get("embeddings") or []
            if embeddings and isinstance(embeddings, list):
                first = embeddings[0]
                if isinstance(first, list):
                    return [float(v) for v in first]
        except urllib.error.URLError:
            pass
        # Stable fallback embedding for offline/local tests.
        seed = sum(ord(c) for c in text)
        return [float((seed * (i + 7)) % 97) / 97.0 for i in range(16)]

    def tool_call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            f"You are routing a tool call.\n"
            f"Tool: {tool_name}\n"
            f"Payload: {json.dumps(payload, sort_keys=True)}\n"
            f"Return a compact JSON object with keys: action, rationale."
        )
        message = self.generate(prompt)
        return {"tool": tool_name, "payload": payload, "status": "delegated", "model_message": message}

