"""Base runner contract for concrete agent backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .agent_run import AgentRun


class AgentRunner(ABC):
    """Abstract runner that executes prompts and returns structured runs."""

    def execute(self, text: str, *, timeout: int, workdir: str | None) -> AgentRun:
        """Execute one prompt and return a normalized run result."""
        return self._execute(text, timeout=timeout, workdir=workdir)

    @abstractmethod
    def _execute(self, text: str, *, timeout: int, workdir: str | None) -> AgentRun: ...
