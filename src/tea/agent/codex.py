from __future__ import annotations

import os
import shlex

from tea.executor import DockerSpec, RawResult
from tea.executor.docker import DockerExecutor

from ._version import resolve_cli_version
from .agent import Agent
from .agent_run import AgentRun, Step
from .harness import ApiKeyHarness, Harness

_NODE_VERSION = "22"
_CODEX_PACKAGE = "@openai/codex"
_CODEX_VERSION_ENV = "CODEX_VERSION"
_DEFAULT_MODEL = "gpt-5.3-codex"


class Codex(Agent):
    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    def build_spec(
        self, prompt: str, timeout: int, skills: list[str] = ()
    ) -> DockerSpec:
        npm_prefix = "/home/node/.npm-global"
        env: dict[str, str] = {"HOME": "/home/node", "NPM_CONFIG_PREFIX": npm_prefix}
        if api_key := os.environ.get("OPENAI_API_KEY"):
            env["OPENAI_API_KEY"] = api_key

        version = self.version()
        image = f"tea-codex:{version}"

        return DockerSpec(
            command=(
                f"{npm_prefix}/bin/codex exec"
                f" --dangerously-bypass-approvals-and-sandbox"
                f" --skip-git-repo-check --ephemeral"
                f" -m {shlex.quote(self._model)}"
                f' "{_esc(prompt)}"'
            ),
            setup_command=_skill_setup(skills) if skills else None,
            dockerfile=self._dockerfile(version),
            env=env,
            image=image,
            user="node",
            timeout=timeout,
        )

    def _dockerfile(self, version: str) -> str:
        return (
            f"FROM node:{_NODE_VERSION}\n"
            "ENV NPM_CONFIG_PREFIX=/home/node/.npm-global\n"
            f"RUN npm install -g {_CODEX_PACKAGE}@{version} --quiet 2>/dev/null\n"
        )

    def version(self) -> str:
        return resolve_cli_version(
            "codex --version", _CODEX_PACKAGE, _CODEX_VERSION_ENV
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


def _skill_setup(skills: list[str]) -> str:
    """Shell commands to install skills into ~/.codex/skills/ inside the container.

    Copies from /workspace/.claude/skills/<name>/SKILL.md (the mounted workdir)
    into the Codex native skill location so Codex loads them automatically.
    """
    cmds = []
    for name in skills:
        # shlex.quote protects the shell word but not the path: a name like
        # "../evil" would still be interpreted as a path traversal once the
        # shell strips the quotes. Reject any name containing a path separator.
        if "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"Invalid skill name: {name!r}")
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
