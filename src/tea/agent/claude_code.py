from __future__ import annotations

import json
import os
import shlex
from dataclasses import replace

from tea.executor import (
    ExecutionRequirements,
    ExecutionSpec,
    RawResult,
)
from tea.executor.docker_executor import DockerExecutor, DockerProfile

from ._utils import _sanitize_env_value
from ._version import resolve_cli_version
from .agent import Agent
from .agent_run import AgentRun, Step, StepType, ToolCall
from .harness import ApiKeyHarness, Harness

_NODE_VERSION = "22"
_CLAUDE_CODE_PACKAGE = "@anthropic-ai/claude-code"
_CLAUDE_CODE_VERSION_ENV = "CLAUDE_CODE_VERSION"
_DEFAULT_MAX_TURNS = 25
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_NPM_PREFIX = "/home/node/.npm-global"

# DockerExecutor mounts the workdir at this path; install_skills relies on it.
_CONTAINER_WORKDIR = "/workspace"
# Where Claude Code's CLI looks for project skills inside the container cwd.
_CLAUDE_NATIVE_PROJECT_SKILLS = ".claude/skills"


def _resolve_version() -> str:
    return resolve_cli_version(
        "claude --version", _CLAUDE_CODE_PACKAGE, _CLAUDE_CODE_VERSION_ENV
    )


def _dockerfile(version: str) -> str:
    return (
        f"FROM node:{_NODE_VERSION}\n"
        f"ENV NPM_CONFIG_PREFIX={_NPM_PREFIX}\n"
        f"RUN npm install -g {_CLAUDE_CODE_PACKAGE}@{version} --quiet 2>/dev/null\n"
    )


def _claude_docker_profile() -> DockerProfile:
    """Static Docker knowledge for Claude Code, resolved lazily.

    A callable (not a constant) so the version probe — a subprocess — runs at
    execution time, never at import time.
    """
    version = _resolve_version()
    return DockerProfile(
        image=f"tea-claude-code:{version}",
        dockerfile=_dockerfile(version),
        user="node",
        env_overrides={"HOME": "/home/node", "NPM_CONFIG_PREFIX": _NPM_PREFIX},
    )


class ClaudeCode(Agent):
    DEFAULT_SKILL_SOURCES = (".claude/skills", ".agents/skills")

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        max_turns: int = _DEFAULT_MAX_TURNS,
        extra_volumes: dict[str, str] | None = None,
    ) -> None:
        self._model = model
        self._max_turns = max_turns
        self._extra_volumes: dict[str, str] = (
            dict(extra_volumes) if extra_volumes else {}
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def max_turns(self) -> int:
        return self._max_turns

    def build_spec(self, prompt: str, timeout: int) -> ExecutionSpec:
        env: dict[str, str] = {}
        if key := os.environ.get("ANTHROPIC_API_KEY"):
            env["ANTHROPIC_API_KEY"] = key
        if token := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token

        env["CLAUDE_PROMPT"] = _sanitize_env_value(prompt)

        return ExecutionSpec(
            command=(
                f"{_NPM_PREFIX}/bin/claude --dangerously-skip-permissions"
                f" --model {shlex.quote(self._model)}"
                f" --max-turns {int(self._max_turns)}"
                ' --print --output-format stream-json --verbose "$CLAUDE_PROMPT"'
            ),
            env=env,
            timeout=timeout,
            requirements=ExecutionRequirements(
                extra_mounts=dict(self._extra_volumes)
            ),
        )

    def install_skills(
        self,
        spec: ExecutionSpec,
        prompt: str,
        workdir: str,
        skills: list[str],
        source_for: dict[str, str],
    ) -> tuple[ExecutionSpec, str]:
        """Materialise skills into ``/workspace/.claude/skills/`` for Claude Code.

        Claude Code's CLI auto-discovers project skills from ``<cwd>/.claude/skills/``.
        Tea's container cwd is ``/workspace`` (the bind-mounted workdir copy).
        Skills discovered in that native path need no copy; skills from any
        other source are translated into the path the CLI scans.
        """
        dst_base = f"{_CONTAINER_WORKDIR}/{_CLAUDE_NATIVE_PROJECT_SKILLS}"
        cmds: list[str] = []
        for name in skills:
            src_dir = source_for[name]
            if os.path.normpath(src_dir) == _CLAUDE_NATIVE_PROJECT_SKILLS:
                continue
            q = shlex.quote(name)
            src = f"{shlex.quote(f'{_CONTAINER_WORKDIR}/{src_dir}')}/{q}/SKILL.md"
            dst_dir = f"{shlex.quote(dst_base)}/{q}"
            cmds.append(f"mkdir -p {dst_dir} && cp {src} {dst_dir}/SKILL.md")
        if not cmds:
            return spec, prompt
        skill_cmd = f"mkdir -p {shlex.quote(dst_base)} && " + " && ".join(cmds)
        merged = (
            f"{spec.setup_command} && {skill_cmd}" if spec.setup_command else skill_cmd
        )
        return replace(spec, setup_command=merged), prompt

    def version(self) -> str:
        return _resolve_version()

    def parse(self, raw: RawResult) -> AgentRun:
        run = self._parse(raw.stdout)
        run.exit_code = raw.exit_code
        run.stderr = raw.stderr
        run.duration_s = raw.duration_s
        return run

    @staticmethod
    def _skill_from_tool(tc: ToolCall) -> str | None:
        if tc.name == "Skill":
            skill = tc.input.get("skill")
            if isinstance(skill, str) and skill:
                return skill
        if tc.name == "Bash":
            cmd = tc.input.get("command", "")
            if isinstance(cmd, str) and cmd.startswith("/"):
                return cmd.split()[0]
        return None

    @staticmethod
    def _parse(stdout: str) -> AgentRun:
        steps: list[Step] = []
        tools: list[ToolCall] = []
        skills: list[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "assistant":
                for block in msg.get("message", {}).get("content", []):
                    block_type = block.get("type")
                    if block_type == "text":
                        steps.append(
                            Step(type=StepType.TEXT, content=block["text"], raw=block)
                        )
                    elif block_type == "tool_use":
                        tc = ToolCall(
                            name=block["name"],
                            input=block.get("input", {}),
                            tool_use_id=block["id"],
                        )
                        tools.append(tc)
                        steps.append(
                            Step(
                                type=StepType.TOOL_USE,
                                content=json.dumps(block.get("input", {})),
                                raw=block,
                            )
                        )
                        skill = ClaudeCode._skill_from_tool(tc)
                        if skill and skill not in skills:
                            skills.append(skill)

            elif msg_type == "tool_result":
                content = msg.get("content", "")
                if isinstance(content, list):
                    text = " ".join(
                        b.get("text", "") for b in content if b.get("type") == "text"
                    )
                else:
                    text = str(content)
                steps.append(Step(type=StepType.TOOL_RESULT, content=text, raw=msg))

        return AgentRun(raw=stdout, steps=steps, tools=tools, skills=skills)


class ClaudeCodeHarness(ApiKeyHarness):
    def with_model(self, model: str) -> Harness:
        agent = self._agent
        max_turns = (
            agent.max_turns if isinstance(agent, ClaudeCode) else _DEFAULT_MAX_TURNS
        )
        return Harness(
            ClaudeCode(model=model, max_turns=max_turns),
            DockerExecutor(_claude_docker_profile),
            skills_sources=self.skills_sources,
        )

    def with_api_key(self) -> Harness:
        agent = self._agent
        model = agent.model if isinstance(agent, ClaudeCode) else _DEFAULT_MODEL
        max_turns = (
            agent.max_turns if isinstance(agent, ClaudeCode) else _DEFAULT_MAX_TURNS
        )
        return Harness(
            ClaudeCode(model=model, max_turns=max_turns),
            DockerExecutor(_claude_docker_profile),
            skills_sources=self.skills_sources,
        )
