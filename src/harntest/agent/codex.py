from __future__ import annotations

import os

from harntest.executor import DockerSpec, RawResult
from harntest.executor.docker import DockerExecutor

from .agent import Agent
from .agent_run import AgentRun, Step
from .harness import ApiKeyHarness, Harness

_CODEX_IMAGE = "node:22"
_DEFAULT_MODEL = "gpt-5.3-codex"


class Codex(Agent):
    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    def build_spec(self, prompt: str, timeout: int) -> DockerSpec:
        npm_prefix = "/home/node/.npm-global"
        env: dict[str, str] = {"HOME": "/home/node", "NPM_CONFIG_PREFIX": npm_prefix}
        if api_key := os.environ.get("OPENAI_API_KEY"):
            env["OPENAI_API_KEY"] = api_key
        return DockerSpec(
            command=(
                f"{npm_prefix}/bin/codex exec"
                f" --dangerously-bypass-approvals-and-sandbox"
                f" --skip-git-repo-check --ephemeral"
                f" -m {self._model}"
                f' "{_esc(prompt)}"'
            ),
            setup_command="npm install -g @openai/codex --quiet 2>/dev/null",
            env=env,
            image=_CODEX_IMAGE,
            user="node",
            timeout=timeout,
        )

    def parse(self, raw: RawResult) -> AgentRun:
        steps = _parse_output(raw.stdout)
        run = AgentRun(raw=raw.stdout, steps=steps, tools=[], skills=[])
        run.exit_code = raw.exit_code
        run.stderr = raw.stderr
        run.duration_s = raw.duration_s
        return run


class CodexHarness(ApiKeyHarness):
    def with_api_key(self) -> Harness:
        model = self._agent._model if isinstance(self._agent, Codex) else _DEFAULT_MODEL
        return Harness(Codex(model=model), DockerExecutor())


def _parse_output(stdout: str) -> list[Step]:
    steps: list[Step] = []
    for line in stdout.splitlines():
        line = line.strip()
        if line:
            steps.append(Step(type="text", content=line, raw={}))
    return steps


def _esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
