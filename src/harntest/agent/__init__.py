from .agent import Agent
from .claude_code import ClaudeCode, ClaudeCodeRunner
from .harness import Harness
from .run_builder import RunBuilder
from harntest.executor.docker import DockerExecutor


class _AgentCatalog:
    ClaudeCode: Harness = Harness(ClaudeCode(), DockerExecutor())
