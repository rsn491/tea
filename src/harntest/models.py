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
class FileDiff:
    added: str
    removed: str


@dataclass
class FileChange:
    path: str
    diff: FileDiff


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int


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
    files_changed: dict[str, FileChange] = field(default_factory=dict)
    duration_s: float = 0.0

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def token_count(self) -> int:
        total_text = " ".join(s.content for s in self.steps)
        return round(len(total_text.split()) * 0.75)

    def diff(self, path: str) -> str:
        change = self.files_changed.get(path)
        if change is None:
            return ""
        lines: list[str] = []
        for line in change.diff.removed.splitlines(keepends=True):
            lines.append("-" + line)
        for line in change.diff.added.splitlines(keepends=True):
            lines.append("+" + line)
        return "".join(lines)
