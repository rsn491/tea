from __future__ import annotations

import os
import shlex
from dataclasses import replace

from tea.executor import DockerSpec, RawResult
from tea.executor.docker_executor import DockerExecutor

from ._utils import _esc
from ._version import resolve_cli_version
from .agent import Agent
from .agent_run import AgentRun, Step, StepType
from .harness import ApiKeyHarness, Harness

_NODE_VERSION = "22"
_CODEX_PACKAGE = "@openai/codex"
_CODEX_VERSION_ENV = "CODEX_VERSION"
_DEFAULT_MODEL = "gpt-5.3-codex"

# DockerExecutor mounts the workdir at this path; install_skills relies on it.
_CONTAINER_WORKDIR = "/workspace"


class Codex(Agent):
    DEFAULT_SKILL_SOURCES = (".codex/skills", ".agents/skills")

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    @property
    def model(self) -> str:
        return self._model

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
        skills: list[str],
        source_for: dict[str, str],
    ) -> tuple[DockerSpec, str]:
        """Copy project skills from the mounted workdir into Codex's native path.

        Codex loads skills from ``~/.codex/skills/<name>/SKILL.md``. The workdir
        is mounted at ``/workspace``, so each ``SKILL.md`` is read from the
        source path it was discovered in (``/workspace/<source_for[name]>/``)
        and copied into Codex's skill directory at container start.
        """
        skill_cmd = _skill_setup(skills, source_for)
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
        agent = self._agent
        model = agent.model if isinstance(agent, Codex) else _DEFAULT_MODEL
        return Harness(
            Codex(model=model),
            DockerExecutor(),
            skills_sources=self.skills_sources,
        )


def _skill_setup(skills: list[str], source_for: dict[str, str]) -> str:
    """Build the shell prelude that installs skills into ``~/.codex/skills/``.

    Reads ``/workspace/<source_for[name]>/<name>/SKILL.md`` (mounted workdir)
    and copies into Codex's native location so the CLI picks them up.
    """
    cmds = []
    for name in skills:
        src_base = f"{_CONTAINER_WORKDIR}/{source_for[name]}"
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
            steps.append(Step(type=StepType.TEXT, content=line, raw={}))
    return steps
