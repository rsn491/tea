from __future__ import annotations

import json
import os

from harntest.infra import DockerRunConfig, run_in_docker

from .agent_run import AgentRun, Step, ToolCall
from .agent_runner import AgentRunner
from .run_builder import RunBuilder

_CLAUDE_IMAGE = "node:22"
_CONTAINER_WORKDIR = "/workspace"
_DEFAULT_MAX_TURNS = 25


class ClaudeCodeRunner(AgentRunner):
    def prompt(self, text: str, *, timeout: int = 300) -> RunBuilder:
        return RunBuilder.prompt(self, text, timeout=timeout)

    def _execute(self, text: str, *, timeout: int, workdir: str | None) -> AgentRun:
        env: dict[str, str] = {}
        api_key = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if api_key:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = api_key

        volumes: dict[str, str] = {}
        container_cwd: str | None = None
        if workdir:
            volumes[workdir] = _CONTAINER_WORKDIR
            container_cwd = _CONTAINER_WORKDIR

        # Run as non-root: --dangerously-skip-permissions is blocked for root.
        # node:22 ships a `node` user; install to a user-local npm prefix so
        # root write access to /usr/local is not required.
        _npm_prefix = "/home/node/.npm-global"
        env["HOME"] = "/home/node"
        env["NPM_CONFIG_PREFIX"] = _npm_prefix
        run_cmd = (
            f"npm install -g @anthropic-ai/claude-code --quiet 2>/dev/null"
            f" && {_npm_prefix}/bin/claude --dangerously-skip-permissions"
            f" --model claude-haiku-4-5-20251001 --max-turns {_DEFAULT_MAX_TURNS}"
            f' --print --output-format stream-json --verbose "{_esc(text)}"'
        )
        config = DockerRunConfig(
            image=_CLAUDE_IMAGE,
            command=["sh", "-c", run_cmd],
            env=env,
            timeout=timeout,
            volumes=volumes,
            container_workdir=container_cwd,
            user="node",
        )
        result = run_in_docker(config)
        run = self._parse(result.stdout)
        run.exit_code = result.exit_code
        run.stderr = result.stderr
        run.duration_s = result.duration_s
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
                        skill = ClaudeCodeRunner._skill_from_tool(tc)
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


def _esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
