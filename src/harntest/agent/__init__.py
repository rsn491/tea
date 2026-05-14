from harntest.executor.docker import DockerExecutor

from .agent import Agent as Agent
from .claude_code import ClaudeCode
from .harness import Harness
from .run_builder import RunBuilder as RunBuilder


class Agents:
    ClaudeCode: Harness = Harness(ClaudeCode(), DockerExecutor())
