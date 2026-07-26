from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import replace
from typing import Self

from tea.executor import WORKDIR_MOUNT, ExecutionSpec, RawResult
from tea.executor.docker_executor import DockerExecutor, DockerProfile

from ._utils import _sanitize_env_value
from ._version import resolve_cli_version
from .agent import Agent
from .agent_run import AgentRun, Step, StepType, ToolCall
from .harness import ApiKeyHarness

_NODE_VERSION = "22"
_CODEX_PACKAGE = "@openai/codex"
_CODEX_VERSION_ENV = "CODEX_VERSION"
_DEFAULT_MODEL = "gpt-5.2-codex"
_CONTAINER_HOME = "/home/node"
_NPM_PREFIX = f"{_CONTAINER_HOME}/.npm-global"
_CODEX_NATIVE_SKILLS_DIR = f"{_CONTAINER_HOME}/.codex/skills"


def _resolve_version() -> str:
    return resolve_cli_version("codex --version", _CODEX_PACKAGE, _CODEX_VERSION_ENV)


def _dockerfile(version: str) -> str:
    return (
        f"FROM node:{_NODE_VERSION}\n"
        f"ENV NPM_CONFIG_PREFIX={_NPM_PREFIX}\n"
        f"RUN npm install -g {_CODEX_PACKAGE}@{version} --quiet 2>/dev/null\n"
    )


def codex_docker_profile(agent: Codex) -> DockerProfile:
    """Static Docker knowledge for Codex, resolved lazily (see ClaudeCode).

    Prefer ``CodexHarness.docker()`` over wiring this into a ``DockerExecutor``
    by hand — see that method for why.
    """
    version = agent.version()
    return DockerProfile(
        image=f"tea-codex:{version}",
        dockerfile=_dockerfile(version),
        user="node",
    )


class Codex(Agent):
    DEFAULT_SKILL_SOURCES = (".codex/skills", ".agents/skills")

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def copy(self, *, model: str | None = None) -> Self:
        """Return a copy with the given fields overridden, keeping the rest."""
        return type(self)(model=self._model if model is None else model)

    def build_spec(self, prompt: str, timeout: int) -> ExecutionSpec:
        # The environment the codex CLI itself needs, independent of who runs
        # it: any executor handed this spec must set it, so it belongs here
        # rather than in a Docker profile.
        env: dict[str, str] = {
            "HOME": _CONTAINER_HOME,
            "NPM_CONFIG_PREFIX": _NPM_PREFIX,
        }
        # API-key auth: forward OPENAI_API_KEY (recommended for programmatic use).
        if api_key := os.environ.get("OPENAI_API_KEY"):
            env["OPENAI_API_KEY"] = api_key

        env["CODEX_PROMPT"] = _sanitize_env_value(prompt)

        return ExecutionSpec(
            command=(
                f"{_NPM_PREFIX}/bin/codex exec --json"
                f" --dangerously-bypass-approvals-and-sandbox"
                f" --skip-git-repo-check --ephemeral"
                f" -m {shlex.quote(self._model)}"
                ' "$CODEX_PROMPT"'
            ),
            env=env,
            timeout=timeout,
        )

    def install_skills(
        self,
        spec: ExecutionSpec,
        prompt: str,
        workdir: str,
        skills: list[str],
        source_for: dict[str, str],
    ) -> tuple[ExecutionSpec, str]:
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

    def version(self) -> str:
        return _resolve_version()

    def parse(self, raw: RawResult) -> AgentRun:
        run = _parse(raw.stdout)
        run.exit_code = raw.exit_code
        run.stderr = raw.stderr
        run.duration_s = raw.duration_s
        return run


class CodexHarness(ApiKeyHarness):
    @classmethod
    def docker(
        cls, agent: Codex | None = None, *, skills_sources: list[str] | None = None
    ) -> Self:
        """Pair a ``Codex`` agent with the Docker image built for it.

        The single place agent and image are wired together — see
        ``ClaudeCodeHarness.docker``.
        """
        agent = agent if agent is not None else Codex()
        return cls(
            agent,
            DockerExecutor(lambda: codex_docker_profile(agent)),
            skills_sources=skills_sources,
        )

    def with_model(self, model: str) -> Self:
        return self._rebuild(self._codex_agent().copy(model=model))

    def with_api_key(self) -> Self:
        return self._rebuild(self._codex_agent().copy())

    def _rebuild(self, agent: Codex) -> Self:
        """Re-wire this harness around ``agent`` — see ``ClaudeCodeHarness``."""
        if isinstance(self._executor, DockerExecutor):
            return type(self).docker(agent, skills_sources=self.skills_sources)
        return type(self)(agent, self._executor, skills_sources=self.skills_sources)

    def _codex_agent(self) -> Codex:
        agent = self._agent
        return agent if isinstance(agent, Codex) else Codex()


def _skill_setup(skills: list[str], source_for: dict[str, str]) -> str:
    """Build the shell prelude that installs skills into ``~/.codex/skills/``.

    Reads ``/workspace/<source_for[name]>/<name>/SKILL.md`` (mounted workdir)
    and copies into Codex's native location so the CLI picks them up.
    """
    cmds = []
    for name in skills:
        # shlex.quote protects the shell word but not the path: a name like
        # "../evil" would still be interpreted as a path traversal once the
        # shell strips the quotes. Reject any name containing a path separator.
        if "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"Invalid skill name: {name!r}")
        src_base = f"{WORKDIR_MOUNT}/{source_for[name]}"
        quoted = shlex.quote(name)
        src = f"{shlex.quote(src_base)}/{quoted}/SKILL.md"
        dst_dir = f"{_CODEX_NATIVE_SKILLS_DIR}/{quoted}"
        cmds.append(f"mkdir -p {dst_dir} && cp {src} {dst_dir}/SKILL.md")
    return " && ".join(cmds)


_SKILL_PATH_RE = re.compile(r"(?:^|[\s/\"'])skills/([A-Za-z0-9_.-]+)/SKILL\.md")


def _parse(stdout: str) -> AgentRun:
    """Parse codex's ``--json`` JSONL event stream.

    Codex emits one event per line: ``thread.started``, ``turn.started``,
    ``item.started`` / ``item.completed`` (with an ``item.type`` of
    ``agent_message``, ``reasoning``, ``command_execution``, ``file_change``,
    ``mcp_tool_call``, ``web_search``, ``todo_list``, ``error``), and
    ``turn.completed`` / ``turn.failed``. See
    https://developers.openai.com/codex/noninteractive.
    """
    steps: list[Step] = []
    tools: list[ToolCall] = []
    skills: list[str] = []

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "item.completed":
            continue

        item = event.get("item") or {}
        item_type = item.get("type")
        item_id = str(item.get("id", ""))

        if item_type in ("agent_message", "reasoning"):
            text = item.get("text", "")
            if text:
                steps.append(Step(type=StepType.TEXT, content=text, raw=item))

        elif item_type == "command_execution":
            command = item.get("command", "")
            tool_input = {"command": command}
            tc = ToolCall(name="bash", input=tool_input, tool_use_id=item_id)
            tools.append(tc)
            steps.append(
                Step(type=StepType.TOOL_USE, content=json.dumps(tool_input), raw=item)
            )
            steps.append(
                Step(
                    type=StepType.TOOL_RESULT,
                    content=item.get("aggregated_output", ""),
                    raw=item,
                )
            )
            for match in _SKILL_PATH_RE.finditer(command):
                name = match.group(1)
                if name not in skills:
                    skills.append(name)

        elif item_type == "file_change":
            changes = item.get("changes", [])
            tool_input = {"changes": changes}
            tc = ToolCall(name="apply_patch", input=tool_input, tool_use_id=item_id)
            tools.append(tc)
            steps.append(
                Step(type=StepType.TOOL_USE, content=json.dumps(tool_input), raw=item)
            )

        elif item_type == "mcp_tool_call":
            tool_name = item.get("tool") or item.get("tool_name", "")
            args = item.get("arguments") or {}
            if not isinstance(args, dict):
                args = {}
            tc = ToolCall(name=tool_name, input=args, tool_use_id=item_id)
            tools.append(tc)
            steps.append(
                Step(type=StepType.TOOL_USE, content=json.dumps(args), raw=item)
            )
            result = item.get("result")
            if result is not None:
                content = (
                    json.dumps(result) if isinstance(result, dict) else str(result)
                )
                steps.append(Step(type=StepType.TOOL_RESULT, content=content, raw=item))

        elif item_type == "web_search":
            query = item.get("query", "")
            tool_input = {"query": query}
            tc = ToolCall(name="web_search", input=tool_input, tool_use_id=item_id)
            tools.append(tc)
            steps.append(
                Step(type=StepType.TOOL_USE, content=json.dumps(tool_input), raw=item)
            )

    return AgentRun(raw=stdout, steps=steps, tools=tools, skills=skills)
