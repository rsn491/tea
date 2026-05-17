from tea.executor.docker import DockerExecutor

from .agent import Agent as Agent
from .claude_code import _CLAUDE_DOCKER_PROFILE, ClaudeCode, ClaudeCodeHarness
from .codex import _CODEX_DOCKER_PROFILE, Codex, CodexHarness
from .harness import Harness as Harness
from .pi import Pi as Pi
from .pi import PiConfig as PiConfig
from .pi import PiHarness
from .run_builder import RunBuilder as RunBuilder


class Agents:
    ClaudeCode: ClaudeCodeHarness = ClaudeCodeHarness(
        ClaudeCode(), DockerExecutor(_CLAUDE_DOCKER_PROFILE)
    )
    Codex: CodexHarness = CodexHarness(Codex(), DockerExecutor(_CODEX_DOCKER_PROFILE))
    Pi: PiHarness = PiHarness()
