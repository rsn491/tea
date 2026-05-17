from __future__ import annotations

from abc import ABC, abstractmethod

from tea.executor import Executor

from .agent import Agent
from .agent_run import AgentRun
from .run_builder import RunBuilder


class Harness:
    def __init__(self, agent: Agent, executor: Executor) -> None:
        self._agent = agent
        self._executor = executor

    def prompt(self, text: str, *, timeout: int = 300) -> RunBuilder:
        return RunBuilder.prompt(self, text, timeout=timeout)

    def prepare_skills(self, prompt: str, workdir: str, skills: list[str]) -> str:
        return self._agent.prepare_skills(prompt, workdir, skills)

    def _execute(
        self, text: str, *, timeout: int, workdir: str | None, skills: list[str] = ()
    ) -> AgentRun:
        spec = self._agent.build_spec(text, timeout, skills)
        raw = self._executor.run(spec, workdir)
        return self._agent.parse(raw)


class ApiKeyHarness(Harness, ABC):
    @abstractmethod
    def with_api_key(self) -> Harness: ...
