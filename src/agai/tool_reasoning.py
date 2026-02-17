from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tool_registry import MCPToolRegistry


@dataclass
class ToolReasoningOutput:
    tool_name: str
    payload: dict[str, Any]
    ok: bool
    output: Any
    error: str


class ToolReasoningEngine:
    def __init__(self, registry: MCPToolRegistry) -> None:
        self.registry = registry

    def run(self, tool_name: str, payload: dict[str, Any]) -> ToolReasoningOutput:
        result = self.registry.invoke(tool_name, payload)
        return ToolReasoningOutput(
            tool_name=tool_name,
            payload=payload,
            ok=result.ok,
            output=result.output,
            error=result.error,
        )

