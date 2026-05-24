from tea.executor.docker import DockerExecutor

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
      ``Agents.Pi``. Load **zero skills**. Use when you don't want skill
      loading at all.
    * **Configured instance** — ``Agents(skills_dir="skills")``. Returns a
      namespace whose harnesses thread that source path into every run. Tea
      imposes **no default** ``skills_dir``; pick one that matches your repo.
    """

    ClaudeCode: ClaudeCodeHarness = ClaudeCodeHarness(ClaudeCode(), DockerExecutor())
    Codex: CodexHarness = CodexHarness(Codex(), DockerExecutor())
    Pi: PiHarness = PiHarness()

    def __init__(self, *, skills_dir: str | None = None) -> None:
        self.ClaudeCode = ClaudeCodeHarness(
            ClaudeCode(), DockerExecutor(), skills_dir=skills_dir
        )
        self.Codex = CodexHarness(Codex(), DockerExecutor(), skills_dir=skills_dir)
        self.Pi = PiHarness(skills_dir=skills_dir)
