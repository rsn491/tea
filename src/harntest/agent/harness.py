from __future__ import annotations

from harntest.executor import Executor
from .agent import Agent
from .agent_run import AgentRun


class Harness:
    def __init__(self, agent: Agent, executor: Executor) -> None:
        self._agent = agent
        self._executor = executor

    def prompt(self, text: str, *, timeout: int = 300) -> "RunBuilder":
        from .run_builder import RunBuilder
        return RunBuilder.prompt(self, text, timeout=timeout)

    def _execute(self, text: str, *, timeout: int, workdir: str | None) -> AgentRun:
        spec = self._agent.build_spec(text, timeout)
        raw = self._executor.run(spec, workdir)
        return self._agent.parse(raw)
