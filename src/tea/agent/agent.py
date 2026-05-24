from __future__ import annotations

from abc import ABC, abstractmethod

from tea.executor import ExecutionSpec, RawResult

from .agent_run import AgentRun


class Agent(ABC):
    # Conventional, in-workdir paths searched when ``skills_sources`` is None.
    # Subclasses override; the agent-specific path comes first so it wins ties
    # against the cross-agent ``.agents/skills`` fallback.
    DEFAULT_SKILL_SOURCES: tuple[str, ...] = ()

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
        skills: list[str],
        source_for: dict[str, str],
    ) -> tuple[ExecutionSpec, str]:
        """Translate the user-configured skills into agent-native form.

        ``skills`` is the list of skill names discovered across one or more
        sources. ``source_for`` maps each skill name to the source directory
        (relative to ``workdir``) it was discovered in — implementations use
        this to build the right copy commands or prompt references when skills
        come from multiple locations (e.g. ``.claude/skills`` and
        ``.agents/skills``).

        Implementations are responsible for materialising the bundles into
        whatever location their CLI expects (a bind mount, a setup command,
        a prompt prefix, etc.) — there is no implicit canonical source path.

        Agents that cannot use skills must raise ``NotImplementedError`` so the
        misconfiguration surfaces to the user instead of being silently dropped.

        Called only when ``workdir`` and ``skills`` are both non-empty.
        """
        ...
