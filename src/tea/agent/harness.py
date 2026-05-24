from __future__ import annotations

from abc import ABC, abstractmethod

from tea.executor import Executor

from .agent import Agent
from .agent_run import AgentRun
from .run_builder import RunBuilder


class Harness:
    def __init__(
        self,
        agent: Agent,
        executor: Executor,
        *,
        skills_dir: str | None = None,
    ) -> None:
        self._agent = agent
        self._executor = executor
        self.skills_dir = skills_dir

    def prompt(self, text: str, *, timeout: int = 300) -> RunBuilder:
        return RunBuilder.prompt(self, text, timeout=timeout)

    def _execute(
        self,
        text: str,
        *,
        timeout: int,
        workdir: str | None,
        skills: list[str] = (),
        skills_dir: str | None = None,
    ) -> AgentRun:
        spec = self._agent.build_spec(text, timeout)
        if skills and workdir and skills_dir:
            spec, text = self._agent.install_skills(
                spec, text, workdir, skills_dir, list(skills)
            )
        raw = self._executor.run(spec, workdir)
        return self._agent.parse(raw)


class ApiKeyHarness(Harness, ABC):
    @abstractmethod
    def with_api_key(self) -> Harness: ...
