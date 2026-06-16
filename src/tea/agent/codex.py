from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import replace

from tea.executor import DockerSpec, RawResult
from tea.executor.docker_executor import DockerExecutor

from ._utils import _esc
from ._version import resolve_cli_version
from .agent import Agent
from .agent_run import AgentRun, Step, StepType, ToolCall
from .harness import ApiKeyHarness, Harness

_NODE_VERSION = "22"
_CODEX_PACKAGE = "@openai/codex"
_CODEX_VERSION_ENV = "CODEX_VERSION"
_DEFAULT_MODEL = "gpt-5.2-codex"

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
        # API-key auth: forward OPENAI_API_KEY (recommended for programmatic use).
        if api_key := os.environ.get("OPENAI_API_KEY"):
            env["OPENAI_API_KEY"] = api_key

        version = self.version()
        image = f"tea-codex:{version}"

        return DockerSpec(
            command=(
                f"{npm_prefix}/bin/codex exec --json"
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
        run = _parse(raw.stdout)
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
