from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    tool_use_id: str


@dataclass
class Step:
    type: str  # "text", "tool_use", "tool_result"
    content: str
    raw: dict[str, Any] = field(repr=False)


@dataclass
class AgentRun:
    raw: str
    steps: list[Step]
    tools: list[ToolCall]
    skills: list[str]
    session_id: str | None = None
    cost_usd: float | None = None
    exit_code: int = 0
    stderr: str = ""
