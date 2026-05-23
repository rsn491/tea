from tea.executor.docker_executor import DockerExecutor

from .agent import Agent as Agent
from .claude_code import ClaudeCode, ClaudeCodeHarness
from .codex import Codex, CodexHarness
from .harness import Harness as Harness
from .model_config import ModelConfig as ModelConfig
from .pi import Pi as Pi
from .pi import PiHarness
from .run_builder import RunBuilder as RunBuilder


class Agents:
    """Catalog of preconfigured harnesses.

    Two forms:

    * **Class-level singletons** — ``Agents.ClaudeCode``, ``Agents.Codex``,
      ``Agents.Pi``. Use the agent's default skill discovery (see below).
    * **Configured instance** — ``Agents(skills_sources=[...])``. Returns a
      namespace whose harnesses use the explicit list of source paths for
      every run, replacing the defaults.

    **Default discovery.** When ``skills_sources`` is ``None`` (the default),
    each harness searches its own conventional, in-workdir paths:

    * ClaudeCode: ``.claude/skills`` then ``.agents/skills``
    * Codex: ``.codex/skills`` then ``.agents/skills``
    * Pi: ``.pi/skills`` then ``.agents/skills``

    Missing default paths are silently skipped. When the same skill name
    appears in more than one source, the earlier source (agent-specific over
    ``.agents/skills``) wins.

    **Opt-out.** Pass ``skills_sources=[]`` to disable skill loading entirely.
    """

    ClaudeCode: ClaudeCodeHarness = ClaudeCodeHarness(ClaudeCode(), DockerExecutor())
    Codex: CodexHarness = CodexHarness(Codex(), DockerExecutor())
    Pi: PiHarness = PiHarness()

    def __init__(self, *, skills_sources: list[str] | None = None) -> None:
        self.ClaudeCode = ClaudeCodeHarness(
            ClaudeCode(), DockerExecutor(), skills_sources=skills_sources
        )
        self.Codex = CodexHarness(
            Codex(), DockerExecutor(), skills_sources=skills_sources
        )
        self.Pi = PiHarness(skills_sources=skills_sources)
