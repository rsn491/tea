from __future__ import annotations

import os
from abc import ABC, abstractmethod

from harntest.docker import DockerRunConfig, run_in_docker
from harntest.models import AgentRun
from harntest.parsers import claude as _claude_parser
from harntest.parsers import codex as _codex_parser

_CLAUDE_IMAGE = "node:22"
_CODEX_IMAGE = "node:22"


class AgentRunner(ABC):
    @abstractmethod
    def prompt(self, text: str, *, timeout: int = 300) -> AgentRun: ...


class ClaudeCodeRunner(AgentRunner):
    def prompt(self, text: str, *, timeout: int = 300) -> AgentRun:
        env: dict[str, str] = {}
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        config = DockerRunConfig(
            image=_CLAUDE_IMAGE,
            command=[
                "sh", "-c",
                "npm install -g @anthropic-ai/claude-code --quiet 2>/dev/null"
                f' && claude --print --output-format stream-json "{_esc(text)}"',
            ],
            env=env,
            timeout=timeout,
        )
        result = run_in_docker(config)
        run = _claude_parser.parse(result.stdout)
        run.exit_code = result.exit_code
        run.stderr = result.stderr
        return run


class CodexRunner(AgentRunner):
    def prompt(self, text: str, *, timeout: int = 300) -> AgentRun:
        env: dict[str, str] = {}
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            env["OPENAI_API_KEY"] = api_key
        config = DockerRunConfig(
            image=_CODEX_IMAGE,
            command=[
                "sh", "-c",
                "npm install -g @openai/codex --quiet 2>/dev/null"
                f' && codex --approval-mode full-auto "{_esc(text)}"',
            ],
            env=env,
            timeout=timeout,
        )
        result = run_in_docker(config)
        run = _codex_parser.parse(result.stdout)
        run.exit_code = result.exit_code
        run.stderr = result.stderr
        return run


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")


class Agent:
    ClaudeCode: AgentRunner = ClaudeCodeRunner()
    Codex: AgentRunner = CodexRunner()
