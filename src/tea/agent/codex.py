from __future__ import annotations

import json
import os
import shlex

from tea.executor import ConfigScope, ExecutionRequirements, ExecutionSpec, RawResult
from tea.executor.docker import DockerExecutor, DockerProfile

from .agent import Agent
from .agent_run import AgentRun, Step
from .harness import ApiKeyHarness, Harness

_CODEX_IMAGE = "node:22"
_DEFAULT_MODEL = "gpt-5.3-codex"
_NPM_PREFIX = "/home/node/.npm-global"

_CODEX_DOCKER_PROFILE = DockerProfile(
    image=_CODEX_IMAGE,
    user="node",
    setup_command="npm install -g @openai/codex --quiet 2>/dev/null",
    env_overrides={"HOME": "/home/node", "NPM_CONFIG_PREFIX": _NPM_PREFIX},
)


class Codex(Agent):
    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    def build_spec(
        self, prompt: str, timeout: int, skills: list[str] = ()
    ) -> ExecutionSpec:
        env: dict[str, str] = {}
        config_scopes: list[ConfigScope] = []

        auth_path = os.path.expanduser("~/.codex/auth.json")
        if os.path.isfile(auth_path):
            try:
                with open(auth_path, encoding="utf-8") as fh:
                    auth_content = fh.read()
                json.loads(auth_content)  # validate
                config_scopes.append(
                    ConfigScope(
                        env_var="CODEX_HOME",
                        files={"auth.json": auth_content},
                    )
                )
            except (OSError, json.JSONDecodeError):
                pass

        if api_key := os.environ.get("OPENAI_API_KEY"):
            env["OPENAI_API_KEY"] = api_key

        return ExecutionSpec(
            command=(
                f"{_NPM_PREFIX}/bin/codex exec"
                f" --dangerously-bypass-approvals-and-sandbox"
                f" --skip-git-repo-check --ephemeral"
                f" -m {shlex.quote(self._model)}"
                f' "{_esc(prompt)}"'
            ),
            env=env,
            timeout=timeout,
            setup_command=_skill_setup(skills) if skills else None,
            requirements=ExecutionRequirements(config_scopes=config_scopes),
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
    """Install skills into $CODEX_HOME/skills/ inside the container."""
    cmds = []
    for name in skills:
        quoted = shlex.quote(name)
        src = f"/workspace/.claude/skills/{quoted}/SKILL.md"
        dst = f'"$CODEX_HOME"/skills/{quoted}'
        cmds.append(f"mkdir -p {dst} && cp {src} {dst}/SKILL.md")
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
