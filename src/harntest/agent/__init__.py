"""Agent runner exports and convenience entry points."""

from .agent_runner import AgentRunner
from .claude_code import ClaudeCodeRunner
from .run_builder import RunBuilder


class Agent:
    """Namespace for built-in runner instances."""

    ClaudeCode: AgentRunner = ClaudeCodeRunner()

    @classmethod
    def available(cls) -> dict[str, AgentRunner]:
        """Return available named runner instances."""
        return {"ClaudeCode": cls.ClaudeCode}
