from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolResult:
    ok: bool
    output: Any
    error: str = ""


class MCPToolRegistry:
    """
    Lightweight MCP-compatible registry.
    The shape mirrors MCP concepts: discoverable schema + callable function.
    """

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSpec, Callable[[dict[str, Any]], Any]]] = {}
        self._unsafe_pattern = re.compile(r"(?i)ignore previous|exfiltrate|system prompt|jailbreak")

    def register(self, spec: ToolSpec, fn: Callable[[dict[str, Any]], Any]) -> None:
        self._tools[spec.name] = (spec, fn)

    def list_specs(self) -> list[ToolSpec]:
        return [spec for spec, _ in self._tools.values()]

    def invoke(self, tool_name: str, payload: dict[str, Any]) -> ToolResult:
        if tool_name not in self._tools:
            return ToolResult(ok=False, output=None, error=f"Tool '{tool_name}' not found.")
        payload_text = str(payload)
        if self._unsafe_pattern.search(payload_text):
            return ToolResult(ok=False, output=None, error="Potential prompt-injection signature detected.")
        spec, fn = self._tools[tool_name]
        required = set(spec.input_schema.get("required", []))
        if not required.issubset(set(payload.keys())):
            missing = sorted(required - set(payload.keys()))
            return ToolResult(ok=False, output=None, error=f"Missing required fields: {missing}")
        try:
            return ToolResult(ok=True, output=fn(payload))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, output=None, error=f"Tool '{tool_name}' failed: {exc}")

