"""Shared data structures for a single agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Callable


@dataclass
class ToolCall:
    """One tool invocation emitted by the agent."""

    name: str
    input: dict[str, Any]
    tool_use_id: str


@dataclass
class Step:
    """One parsed output step from the agent stream."""

    type: str  # "text", "tool_use", "tool_result"
    content: str
    raw: dict[str, Any] = field(repr=False)


@dataclass
class FileDiff:
    """Added and removed text for a file diff."""

    added: str
    removed: str


@dataclass
class FileChange:
    """File path plus text diff payload."""

    path: str
    diff: FileDiff


@dataclass
class AgentRun:
    """Parsed agent output plus execution metadata."""

    raw: str
    steps: list[Step]
    tools: list[ToolCall]
    skills: list[str]
    exit_code: int = 0
    stderr: str = ""
    duration_s: float = 0.0
    _files_changed_fn: Callable[[], dict[str, FileChange]] = field(
        default=lambda: {}, repr=False, compare=False
    )

    @cached_property
    def files_changed(self) -> dict[str, FileChange]:
        """Compute file changes lazily from captured snapshots."""
        return self._files_changed_fn()

    def set_files_changed_resolver(
        self, resolver: Callable[[], dict[str, FileChange]]
    ) -> None:
        """Override lazy file-diff resolver for this run."""
        self._files_changed_fn = resolver
        self.__dict__.pop("files_changed", None)

    @property
    def step_count(self) -> int:
        """Total number of parsed steps."""
        return len(self.steps)

    @property
    def token_count(self) -> int:
        """Approximate token count based on step text."""
        total_text = " ".join(s.content for s in self.steps)
        return round(len(total_text.split()) * 0.75)
