from __future__ import annotations

from abc import ABC, abstractmethod

from tea.executor import ExecutionSpec, RawResult

from .agent_run import AgentRun


class Agent(ABC):
    @abstractmethod
    def build_spec(self, prompt: str, timeout: int) -> ExecutionSpec: ...

    @abstractmethod
    def parse(self, raw: RawResult) -> AgentRun: ...
