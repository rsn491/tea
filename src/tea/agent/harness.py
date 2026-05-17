from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from tea.executor import Executor

from .agent import Agent

if TYPE_CHECKING:
    from .run_builder import RunBuilder


class Harness:
    """An assembled (agent, executor) pair ready to receive prompts."""

    def __init__(self, agent: Agent, executor: Executor) -> None:
        self._agent = agent
        self._executor = executor

    def prompt(self, text: str, *, timeout: int = 300) -> RunBuilder:
        from .run_builder import RunBuilder  # noqa: PLC0415

        return RunBuilder.prompt(self, text, timeout=timeout)


class ApiKeyHarness(Harness, ABC):
    @abstractmethod
    def with_api_key(self) -> Harness: ...
