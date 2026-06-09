from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from functools import cached_property
from typing import Any, Callable


class StepType(StrEnum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    tool_use_id: str


@dataclass
class Step:
    type: StepType
    content: str
    raw: dict[str, Any] = field(repr=False)


@dataclass
class FileDiff:
    added: str
    removed: str
    unified: str = ""


@dataclass
class FileChange:
    path: str
    diff: FileDiff


@dataclass
class AgentRun:
    raw: str
    steps: list[Step]
    tools: list[ToolCall]
    skills: list[str]
    exit_code: int = 0
    stderr: str = ""
    duration_s: float = 0.0
    _files_changed_fn: Callable[[], dict[str, FileChange]] = field(
        init=False, default=lambda: {}, repr=False, compare=False
    )

    @cached_property
    def files_changed(self) -> dict[str, FileChange]:
        return self._files_changed_fn()

    def diff(self, file: str) -> str:
        change = self.files_changed.get(file)
        return change.diff.unified if change else ""

    @property
    def full_diff(self) -> str:
        """Unified diff across every file changed in the run, concatenated."""
        return "\n".join(
            change.diff.unified
            for change in self.files_changed.values()
            if change.diff.unified
        )

    @property
    def transcript(self) -> str:
        parts = []
        for step in self.steps:
            if step.type == StepType.TEXT:
                parts.append(f"[assistant] {step.content}")
            elif step.type == StepType.TOOL_USE:
                parts.append(f"[tool_use] {step.content}")
            elif step.type == StepType.TOOL_RESULT:
                parts.append(f"[tool_result] {step.content}")
        return "\n".join(parts)

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def token_count(self) -> int:
        total_text = " ".join(s.content for s in self.steps)
        return round(len(total_text.split()) * 0.75)
