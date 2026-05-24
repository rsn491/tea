from __future__ import annotations

from abc import ABC, abstractmethod

from tea.executor import ExecutionSpec, RawResult

from .agent_run import AgentRun


class Agent(ABC):
    @abstractmethod
    def build_spec(self, prompt: str, timeout: int) -> ExecutionSpec: ...

    @abstractmethod
    def parse(self, raw: RawResult) -> AgentRun: ...

    @abstractmethod
    def version(self) -> str:
        """Return the CLI tool version this agent will run inside Docker.

        Resolution is agent-specific (env var override → CLI probe → npm → fallback).
        Called lazily by ``build_spec()`` to build a versioned image tag.
        """
        ...

    @abstractmethod
    def install_skills(
        self,
        spec: ExecutionSpec,
        prompt: str,
        workdir: str,
        skills_dir: str,
        skills: list[str],
    ) -> tuple[ExecutionSpec, str]:
        """Translate the user-configured skills into agent-native form.

        ``skills_dir`` is the user-supplied path (relative to ``workdir``) where
        skill bundles live; ``skills`` is the list of skill names discovered
        there. Implementations are responsible for materialising the bundles
        into whatever location their CLI expects (a bind mount, a setup command,
        a prompt prefix, etc.) — there is no implicit canonical source path.

        Agents that cannot use skills must raise ``NotImplementedError`` so the
        misconfiguration surfaces to the user instead of being silently dropped.

        Called only when ``workdir``, ``skills_dir`` and ``skills`` are all set.
        """
        ...
