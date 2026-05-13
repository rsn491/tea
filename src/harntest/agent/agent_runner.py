from __future__ import annotations

from abc import ABC, abstractmethod

from .agent_run import AgentRun


class AgentRunner(ABC):
    @abstractmethod
    def _execute(self, text: str, *, timeout: int, workdir: str | None) -> AgentRun: ...
