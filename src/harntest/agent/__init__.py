from .agent_runner import AgentRunner
from .claude_code import ClaudeCodeRunner
from .run_builder import RunBuilder as RunBuilder


class Agent:
    ClaudeCode: AgentRunner = ClaudeCodeRunner()
