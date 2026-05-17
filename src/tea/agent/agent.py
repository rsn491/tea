from __future__ import annotations

from abc import ABC, abstractmethod

from tea.executor import ExecutionSpec, RawResult

from .agent_run import AgentRun


class Agent(ABC):
    @abstractmethod
    def build_spec(
        self, prompt: str, timeout: int, skills: list[str] = ()
    ) -> ExecutionSpec:
        """Build the execution spec for this agent.

        Skills can be injected here at the execution level — e.g. passing them
        as CLI flags (ClaudeCode) or copying them as files via setup_command
        (Codex). Agents that handle skills at the prompt level instead use
        prepare_skills() and can ignore the skills argument here.
        """
        ...

    @abstractmethod
    def parse(self, raw: RawResult) -> AgentRun:
        """Parse raw executor output into a structured AgentRun.

        Populate AgentRun.skills with the names of skills actually used during
        the run, if detectable from the output format. Leave it as [] if the
        agent's output does not expose this information.
        """
        ...

    def prepare_skills(self, prompt: str, workdir: str, skills: list[str]) -> str:
        """Inject skills into the prompt before build_spec is called.

        Override this when the agent needs to read skill descriptions from the
        host workdir and surface them in the prompt (e.g. Pi, which has no CLI
        flag for skills). Agents that inject skills at the execution level in
        build_spec() leave this as a no-op.

        Both hooks are independent — an agent may use either, both, or neither.
        """
        return prompt
