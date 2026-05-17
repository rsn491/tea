from __future__ import annotations

import json
import os
import shlex

from tea.executor import ExecutionSpec, RawResult
from tea.executor.docker import DockerExecutor, DockerProfile

from .agent import Agent
from .agent_run import AgentRun, Step, ToolCall
from .harness import ApiKeyHarness, Harness

_CLAUDE_IMAGE = "node:22"
_DEFAULT_MAX_TURNS = 25
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_NPM_PREFIX = "/home/node/.npm-global"

_CLAUDE_DOCKER_PROFILE = DockerProfile(
    image=_CLAUDE_IMAGE,
    user="node",
    setup_command="npm install -g @anthropic-ai/claude-code --quiet 2>/dev/null",
    env_overrides={"HOME": "/home/node", "NPM_CONFIG_PREFIX": _NPM_PREFIX},
)


class ClaudeCode(Agent):
    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        max_turns: int = _DEFAULT_MAX_TURNS,
    ) -> None:
        self._model = model
        self._max_turns = max_turns

    def build_spec(
        self, prompt: str, timeout: int, skills: list[str] = ()
    ) -> ExecutionSpec:
        env: dict[str, str] = {}
        if key := os.environ.get("ANTHROPIC_API_KEY"):
            env["ANTHROPIC_API_KEY"] = key
        if token := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token

        return ExecutionSpec(
            command=(
                f"{_NPM_PREFIX}/bin/claude --dangerously-skip-permissions"
                f" --model {shlex.quote(self._model)}"
                f" --max-turns {int(self._max_turns)}"
                f' --print --output-format stream-json --verbose "{_esc(prompt)}"'
            ),
            env=env,
            timeout=timeout,
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
    def with_model(self, model: str) -> Harness:
        max_turns = (
            self._agent._max_turns
            if isinstance(self._agent, ClaudeCode)
            else _DEFAULT_MAX_TURNS
        )
        return Harness(
            ClaudeCode(model=model, max_turns=max_turns),
            DockerExecutor(_CLAUDE_DOCKER_PROFILE),
        )

    def with_api_key(self) -> Harness:
        agent = self._agent
        model = agent._model if isinstance(agent, ClaudeCode) else _DEFAULT_MODEL
        max_turns = (
            agent._max_turns if isinstance(agent, ClaudeCode) else _DEFAULT_MAX_TURNS
        )
        return Harness(
            ClaudeCode(model=model, max_turns=max_turns),
            DockerExecutor(_CLAUDE_DOCKER_PROFILE),
        )


def _esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
