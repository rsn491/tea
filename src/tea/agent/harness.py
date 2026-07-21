from __future__ import annotations

from abc import ABC, abstractmethod

from tea.executor import Executor

from .agent import Agent
from .run_builder import RunBuilder


class Harness:
    """An assembled (agent, executor) pair ready to receive prompts."""

    def __init__(
        self,
        agent: Agent,
        executor: Executor,
        *,
        skills_sources: list[str] | None = None,
    ) -> None:
        self._agent = agent
        self._executor = executor
        # ``None`` means "use the agent's defaults" (handled in RunBuilder);
        # ``[]`` means "explicit opt-out, no skills"; non-empty list overrides.
        self.skills_sources: list[str] | None = (
            list(skills_sources) if skills_sources is not None else None
        )

    @property
    def default_skill_sources(self) -> tuple[str, ...]:
        """Conventional in-workdir paths the agent searches when no sources set."""
        return type(self._agent).DEFAULT_SKILL_SOURCES

    def prompt(self, text: str, *, timeout: int = 300) -> RunBuilder:
        return RunBuilder.prompt(self, text, timeout=timeout)


class ApiKeyHarness(Harness, ABC):
    @abstractmethod
    def with_api_key(self) -> Harness: ...
