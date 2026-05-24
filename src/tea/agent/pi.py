from __future__ import annotations

import json
import os
import shlex

from tea.executor import DockerSpec, RawResult
from tea.executor.docker import DockerExecutor

from ._version import resolve_cli_version
from .agent import Agent
from .agent_run import AgentRun, Step, ToolCall
from .harness import Harness
from .model_config import ModelConfig

_NODE_VERSION = "22"
_PI_PACKAGE = "pi"
_PI_VERSION_ENV = "PI_VERSION"


class Pi(Agent):
    def __init__(self, model_config: ModelConfig) -> None:
        self._model_config = model_config

    def build_spec(
        self, prompt: str, timeout: int, skills: list[str] = ()
    ) -> DockerSpec:
        npm_prefix = "/home/node/.npm-global"
        env: dict[str, str] = {"HOME": "/home/node", "NPM_CONFIG_PREFIX": npm_prefix}
        api_key: str | None = None
        if self._model_config.api_key_env:
            if key := os.environ.get(self._model_config.api_key_env):
                env[self._model_config.api_key_env] = key
                api_key = key

        extra_hosts: dict[str, str] = {}
        setup_parts: list[str] = []

        if self._model_config.base_url:
            # Write a Pi models.json so Pi knows how to reach the custom provider.
            # The model string must be "provider/model-id"; we derive the provider
            # name from the part before the first slash (e.g. "ollama").
            models_json = _build_models_json(
                self._model_config.model,
                self._model_config.base_url,
                api_key,
            )
            escaped = models_json.replace("'", "'\\''")
            setup_parts.append(
                f"mkdir -p /home/node/.pi/agent"
                f" && printf '%s' '{escaped}' > /home/node/.pi/agent/models.json"
            )
            extra_hosts["host.docker.internal"] = "host-gateway"

        if skills:
            setup_parts.append(_skill_setup(skills))

        setup_command = " && ".join(setup_parts) if setup_parts else None

        version = self.version()
        image = f"tea-pi:{version}"

        return DockerSpec(
            command=(
                f"{npm_prefix}/bin/pi --mode json --no-extensions"
                f" --model {self._model_config.model}"
                f' "{_esc(prompt)}"'
            ),
            setup_command=setup_command,
            dockerfile=self._dockerfile(version),
            env=env,
            image=image,
            user="node",
            timeout=timeout,
            extra_hosts=extra_hosts,
        )

    def _dockerfile(self, version: str) -> str:
        return (
            f"FROM node:{_NODE_VERSION}\n"
            "ENV NPM_CONFIG_PREFIX=/home/node/.npm-global\n"
            f"RUN npm install -g {_PI_PACKAGE}@{version} --quiet 2>/dev/null\n"
        )

    def version(self) -> str:
        return resolve_cli_version("pi --version", _PI_PACKAGE, _PI_VERSION_ENV)

    def parse(self, raw: RawResult) -> AgentRun:
        run = _parse(raw.stdout)
        run.exit_code = raw.exit_code
        run.stderr = raw.stderr
        run.duration_s = raw.duration_s
        return run


class PiHarness:
    """Factory for Pi runs.

    Exposes only ``with_model()``: Pi has no default model and no OAuth/api-key
    fallback path, so a ``ModelConfig`` must always be supplied externally.
    Because ``PiHarness`` does not inherit ``Harness``, ``Agents.Pi.prompt(...)``
    is a static type error — the only valid entry point is
    ``Agents.Pi.with_model(config).prompt(...)``.
    """

    def with_model(self, config: ModelConfig) -> Harness:
        return Harness(Pi(model_config=config), DockerExecutor())


def _build_models_json(model: str, base_url: str, api_key: str | None) -> str:
    """Build a Pi models.json for a custom OpenAI-compatible provider."""
    if "/" in model:
        provider_name, model_id = model.split("/", 1)
    else:
        provider_name, model_id = "custom", model
    config = {
        "providers": {
            provider_name: {
                "baseUrl": base_url,
                "api": "openai-completions",
                "apiKey": api_key or "local",
                "compat": {
                    "supportsDeveloperRole": False,
                    "supportsReasoningEffort": False,
                },
                "models": [{"id": model_id}],
            }
        }
    }
    return json.dumps(config)


def _parse(stdout: str) -> AgentRun:
    steps: list[Step] = []
    tools: list[ToolCall] = []

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")

        if event_type == "message_end":
            # Pi emits message_end for both user and assistant turns; skip user turns.
            message = event.get("message", {})
            if message.get("role") != "assistant":
                continue
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            steps.append(Step(type="text", content=text, raw=event))
            elif isinstance(content, str) and content:
                steps.append(Step(type="text", content=content, raw=event))

        elif event_type == "tool_execution_start":
            tool_name = event.get("toolName", "")
            tool_call_id = event.get("toolCallId", "")
            args = event.get("args", {})
            if not isinstance(args, dict):
                args = {}
            tc = ToolCall(name=tool_name, input=args, tool_use_id=tool_call_id)
            tools.append(tc)
            steps.append(Step(type="tool_use", content=json.dumps(args), raw=event))

        elif event_type == "tool_execution_end":
            result = event.get("result")
            if isinstance(result, dict):
                content = json.dumps(result)
            elif result is not None:
                content = str(result)
            else:
                content = ""
            steps.append(Step(type="tool_result", content=content, raw=event))

    return AgentRun(raw=stdout, steps=steps, tools=tools, skills=[])


def _skill_setup(skills: list[str]) -> str:
    """Shell commands to install skills into ~/.pi/agent/skills/ inside the container.

    Copies from /workspace/.claude/skills/<name>/SKILL.md (the mounted workdir)
    into the Pi native skill location so Pi auto-discovers them at runtime
    (see https://pi.dev/docs/latest/skills#locations).
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
        dst_dir = f"/home/node/.pi/agent/skills/{quoted}"
        cmds.append(f"mkdir -p {dst_dir} && cp {src} {dst_dir}/SKILL.md")
    return " && ".join(cmds)


def _esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
