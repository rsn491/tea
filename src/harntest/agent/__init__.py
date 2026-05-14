from .agent import Agent
from .claude_code import ClaudeCode
from .harness import Harness
from .run_builder import RunBuilder
from harntest.executor.docker import DockerExecutor


class Agents:
    ClaudeCode: Harness = Harness(ClaudeCode(), DockerExecutor())
