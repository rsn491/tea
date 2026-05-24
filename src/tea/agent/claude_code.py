from __future__ import annotations

import json
import os
import shlex
from dataclasses import replace

from tea.executor import DockerSpec, RawResult
from tea.executor.docker import DockerExecutor

from ._version import resolve_cli_version
from .agent import Agent
from .agent_run import AgentRun, Step, ToolCall
from .harness import ApiKeyHarness, Harness

_NODE_VERSION = "22"
_CLAUDE_CODE_PACKAGE = "@anthropic-ai/claude-code"
_CLAUDE_CODE_VERSION_ENV = "CLAUDE_CODE_VERSION"
_DEFAULT_MAX_TURNS = 25
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# DockerExecutor mounts the workdir at this path; install_skills relies on it.
_CONTAINER_WORKDIR = "/workspace"
# Where Claude Code's CLI looks for project skills inside the container cwd.
_CLAUDE_NATIVE_PROJECT_SKILLS = ".claude/skills"


class ClaudeCode(Agent):
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

    def build_spec(self, prompt: str, timeout: int) -> DockerSpec:
        npm_prefix = "/home/node/.npm-global"
        env: dict[str, str] = {"HOME": "/home/node", "NPM_CONFIG_PREFIX": npm_prefix}
        if key := os.environ.get("ANTHROPIC_API_KEY"):
            env["ANTHROPIC_API_KEY"] = key
        if token := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token

        extra_volumes: dict[str, str] = {}
        # Mount only OAuth credentials from the host ~/.claude — not the whole
        # directory, which would leak the developer's personal skills, agents,
        # and settings into the test container.
        host_creds = os.path.expanduser("~/.claude/.credentials.json")
        if os.path.isfile(host_creds):
            extra_volumes[host_creds] = "/home/node/.claude/.credentials.json"
        extra_volumes.update(self._extra_volumes)

        version = self.version()
        image = f"tea-claude-code:{version}"

        return DockerSpec(
            command=(
                f"{npm_prefix}/bin/claude --dangerously-skip-permissions"
                f" --model {shlex.quote(self._model)}"
                f" --max-turns {int(self._max_turns)}"
                f' --print --output-format stream-json --verbose "{_esc(prompt)}"'
            ),
            dockerfile=self._dockerfile(version),
            env=env,
            image=image,
            user="node",
            timeout=timeout,
            extra_volumes=extra_volumes,
        )

    def install_skills(
        self,
        spec: DockerSpec,
        prompt: str,
        workdir: str,
        skills_dir: str,
        skills: list[str],
    ) -> tuple[DockerSpec, str]:
        """Materialise skills into ``/workspace/.claude/skills/`` for Claude Code.

        Claude Code's CLI auto-discovers project skills from ``<cwd>/.claude/skills/``.
        Tea's container cwd is ``/workspace`` (the bind-mounted workdir copy). If
        the user already points ``skills_dir`` at the native location, the copy
        is a no-op — otherwise a setup command translates from the chosen source
        to the path the CLI scans.
        """
        if os.path.normpath(skills_dir) == _CLAUDE_NATIVE_PROJECT_SKILLS:
            return spec, prompt

        src_base = f"{_CONTAINER_WORKDIR}/{skills_dir}"
        dst_base = f"{_CONTAINER_WORKDIR}/{_CLAUDE_NATIVE_PROJECT_SKILLS}"
        cmds = [f"mkdir -p {shlex.quote(dst_base)}"]
        for name in skills:
            q = shlex.quote(name)
            src = f"{shlex.quote(src_base)}/{q}/SKILL.md"
            dst_dir = f"{shlex.quote(dst_base)}/{q}"
            cmds.append(f"mkdir -p {dst_dir} && cp {src} {dst_dir}/SKILL.md")
        skill_cmd = " && ".join(cmds)
        merged = (
            f"{spec.setup_command} && {skill_cmd}" if spec.setup_command else skill_cmd
        )
        return replace(spec, setup_command=merged), prompt

    def _dockerfile(self, version: str) -> str:
        return (
            f"FROM node:{_NODE_VERSION}\n"
            "ENV NPM_CONFIG_PREFIX=/home/node/.npm-global\n"
            f"RUN npm install -g {_CLAUDE_CODE_PACKAGE}@{version} --quiet 2>/dev/null\n"
        )

    def version(self) -> str:
        return resolve_cli_version(
            "claude --version", _CLAUDE_CODE_PACKAGE, _CLAUDE_CODE_VERSION_ENV
        )

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
                            Step(type="text", content=block["text"], raw=block)
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
                                type="tool_use",
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
                steps.append(Step(type="tool_result", content=text, raw=msg))

        return AgentRun(raw=stdout, steps=steps, tools=tools, skills=skills)


class ClaudeCodeHarness(ApiKeyHarness):
    def with_api_key(self) -> Harness:
        agent = self._agent
        model = agent.model if isinstance(agent, ClaudeCode) else _DEFAULT_MODEL
        max_turns = (
            agent.max_turns if isinstance(agent, ClaudeCode) else _DEFAULT_MAX_TURNS
        )
        return Harness(
            ClaudeCode(model=model, max_turns=max_turns),
            DockerExecutor(),
            skills_dir=self.skills_dir,
        )


def _esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
