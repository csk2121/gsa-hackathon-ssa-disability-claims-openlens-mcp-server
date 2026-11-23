"""What one agent run produced. No third-party imports, so the checks stay testable anywhere."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    output: str
    is_error: bool


@dataclass
class AgentRun:
    answer: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    wall_s: float = 0.0  # including process and MCP server start-up (claude-code backend)
    cost_usd: float = 0.0  # API-equivalent cost, when the backend reports it
    turns: int = 0
    stop_reason: str = ""
    error: str = ""

    @property
    def tools_called(self) -> list[str]:
        return [c.name for c in self.tool_calls]
