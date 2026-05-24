from __future__ import annotations

from abc import ABC, abstractmethod

from tea.executor import ExecutionSpec, RawResult

from .agent_run import AgentRun


class Agent(ABC):
    @abstractmethod
    def build_spec(
        self, prompt: str, timeout: int, skills: list[str] = ()
    ) -> ExecutionSpec: ...

    @abstractmethod
    def parse(self, raw: RawResult) -> AgentRun: ...

    @abstractmethod
    def version(self) -> str:
        """Return the CLI tool version this agent will run inside Docker.

        Resolution is agent-specific (env var override → CLI probe → npm → fallback).
        Called lazily by ``build_spec()`` to build a versioned image tag.
        """
        ...

    def prepare_skills(self, prompt: str, workdir: str, skills: list[str]) -> str:
        """Host-side skill preparation called before the agent runs.

        Agents that need to read skill files from the host workdir and modify
        the prompt override this. Agents that handle skills at spec-build time
        (e.g. Codex, which copies skill files into the container) leave this as
        a no-op and handle skills in build_spec instead.
        """
        return prompt
