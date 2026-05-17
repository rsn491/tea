from __future__ import annotations

import os
import shlex

from tea.executor import ExecutionSpec, RawResult
from tea.executor.docker import DockerExecutor, DockerProfile

from .agent import Agent
from .agent_run import AgentRun, Step
from .harness import ApiKeyHarness, Harness

_CODEX_IMAGE = "node:22"
_DEFAULT_MODEL = "gpt-5.3-codex"

_CODEX_DOCKER_PROFILE = DockerProfile(
    image=_CODEX_IMAGE,
    user="node",
    env_overrides={"HOME": "/home/node"},
)


class Codex(Agent):
    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    def build_spec(
        self, prompt: str, timeout: int, skills: list[str] = ()
    ) -> ExecutionSpec:
        env: dict[str, str] = {}
        if api_key := os.environ.get("OPENAI_API_KEY"):
            env["OPENAI_API_KEY"] = api_key
        return ExecutionSpec(
            command=(
                f"codex exec"
                f" --dangerously-bypass-approvals-and-sandbox"
                f" --skip-git-repo-check --ephemeral"
                f" -m {shlex.quote(self._model)}"
                f' "{_esc(prompt)}"'
            ),
            env=env,
            timeout=timeout,
            setup_command=_skill_setup(skills) if skills else None,
        )

    def parse(self, raw: RawResult) -> AgentRun:
        steps = _parse_output(raw.stdout)
        run = AgentRun(raw=raw.stdout, steps=steps, tools=[], skills=[])
        run.exit_code = raw.exit_code
        run.stderr = raw.stderr
        run.duration_s = raw.duration_s
        return run


class CodexHarness(ApiKeyHarness):
    def with_model(self, model: str) -> Harness:
        return Harness(Codex(model=model), DockerExecutor(_CODEX_DOCKER_PROFILE))

    def with_api_key(self) -> Harness:
        model = self._agent._model if isinstance(self._agent, Codex) else _DEFAULT_MODEL
        return Harness(Codex(model=model), DockerExecutor(_CODEX_DOCKER_PROFILE))


def _skill_setup(skills: list[str]) -> str:
    """Shell commands to install skills into ~/.codex/skills/ inside the container."""
    cmds = []
    for name in skills:
        quoted = shlex.quote(name)
        src = f"/workspace/.claude/skills/{quoted}/SKILL.md"
        dst_dir = f"/home/node/.codex/skills/{quoted}"
        cmds.append(f"mkdir -p {dst_dir} && cp {src} {dst_dir}/SKILL.md")
    return " && ".join(cmds)


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
