from __future__ import annotations

import os
import shlex
from dataclasses import replace

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

# DockerExecutor mounts the workdir at this path; install_skills relies on it.
_CONTAINER_WORKDIR = "/workspace"


class Codex(Agent):
    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    def build_spec(self, prompt: str, timeout: int) -> DockerSpec:
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
            dockerfile=self._dockerfile(version),
            env=env,
            image=image,
            user="node",
            timeout=timeout,
        )

    def install_skills(
        self,
        spec: DockerSpec,
        prompt: str,
        workdir: str,
        skills_dir: str,
        skills: list[str],
    ) -> tuple[DockerSpec, str]:
        """Copy project skills from the mounted workdir into Codex's native path.

        Codex loads skills from ``~/.codex/skills/<name>/SKILL.md``. The workdir
        is mounted at ``/workspace``, so each ``SKILL.md`` is read from
        ``/workspace/<skills_dir>/<name>/SKILL.md`` and copied into Codex's
        skill directory at container start.
        """
        skill_cmd = _skill_setup(skills, skills_dir)
        merged_setup = (
            f"{spec.setup_command} && {skill_cmd}" if spec.setup_command else skill_cmd
        )
        return replace(spec, setup_command=merged_setup), prompt

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
        return Harness(Codex(model=model), DockerExecutor(), skills_dir=self.skills_dir)


def _skill_setup(skills: list[str], skills_dir: str) -> str:
    """Build the shell prelude that installs skills into ``~/.codex/skills/``.

    Reads ``/workspace/<skills_dir>/<name>/SKILL.md`` (mounted workdir) and
    copies into Codex's native location so the CLI picks them up.
    """
    src_base = f"{_CONTAINER_WORKDIR}/{skills_dir}"
    cmds = []
    for name in skills:
        quoted = shlex.quote(name)
        src = f"{shlex.quote(src_base)}/{quoted}/SKILL.md"
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
