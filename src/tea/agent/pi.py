from __future__ import annotations

import json
import os
from dataclasses import dataclass

from tea.executor import DockerSpec, ExecutionRequirements, RawResult
from tea.executor.docker import DockerExecutor

from .agent import Agent
from .agent_run import AgentRun, Step, ToolCall
from .harness import Harness

_PI_IMAGE = "node:22"
_PI_PREFIX = "/home/node/.npm-global"
# Install into ~/.npm-global (writable by the node user) and add to PATH.
_PI_INSTALL = (
    f"mkdir -p {_PI_PREFIX}"
    f" && npm install --prefix {_PI_PREFIX} @earendil-works/pi-coding-agent"
    f" --quiet --no-progress >/dev/null 2>&1"
    f" && export PATH={_PI_PREFIX}/node_modules/.bin:$PATH"
)


@dataclass
class PiConfig:
    """Pi-specific model configuration.

    model:       "provider/model-id" string (e.g. "anthropic/claude-sonnet-4-6")
    api_key_env: name of the host env var to forward into the container
    base_url:    OpenAI-compatible endpoint — only needed for non-native providers
                 (Ollama, vLLM, LM Studio).  Native cloud providers (Anthropic,
                 OpenAI, Gemini, etc.) are known to Pi without a base_url.
    """

    model: str
    api_key_env: str | None = None
    base_url: str | None = None


class Pi(Agent):
    def __init__(self, model_config: PiConfig) -> None:
        self._model_config = model_config

    def build_spec(
        self, prompt: str, timeout: int, skills: list[str] = ()
    ) -> DockerSpec:
        env: dict[str, str] = {"HOME": "/home/node"}
        api_key: str | None = None
        if self._model_config.api_key_env:
            if key := os.environ.get(self._model_config.api_key_env):
                env[self._model_config.api_key_env] = key
                api_key = key

        setup_parts: list[str] = [_PI_INSTALL]
        requirements = ExecutionRequirements()

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
            requirements = ExecutionRequirements(host_network_access=True)

        return DockerSpec(
            command=(
                f"pi --mode json --no-extensions"
                f" --model {self._model_config.model}"
                f' "{_esc(prompt)}"'
            ),
            setup_command=" && ".join(setup_parts),
            env=env,
            image=_PI_IMAGE,
            user="node",
            timeout=timeout,
            requirements=requirements,
        )

    def prepare_skills(self, prompt: str, workdir: str, skills: list[str]) -> str:
        entries = []
        for name in skills:
            skill_path = os.path.join(workdir, ".claude", "skills", name, "SKILL.md")
            description = _read_skill_description(skill_path)
            rel_path = f".claude/skills/{name}/SKILL.md"
            entries.append(f"- {name}: {description}\n  Path: {rel_path}")
        if not entries:
            return prompt
        listing = "\n".join(entries)
        preamble = (
            "The following project skills are available to guide your work. "
            "If a skill is relevant to your task, read it at the provided path "
            "and follow its guidance.\n\n"
            f"Available skills:\n{listing}"
        )
        return f"{preamble}\n\n{prompt}"

    def parse(self, raw: RawResult) -> AgentRun:
        run = _parse(raw.stdout)
        run.exit_code = raw.exit_code
        run.stderr = raw.stderr
        run.duration_s = raw.duration_s
        return run


class PiHarness:
    """Factory for Pi runs.

    Exposes only ``with_model()``: Pi has no default model and no OAuth/api-key
    fallback path, so a ``PiConfig`` must always be supplied externally.
    Because ``PiHarness`` does not inherit ``Harness``, ``Agents.Pi.prompt(...)``
    is a static type error — the only valid entry point is
    ``Agents.Pi.with_model(config).prompt(...)``.
    """

    def with_model(self, config: PiConfig) -> Harness:
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


def _read_skill_description(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return ""
    if not content.startswith("---"):
        return ""
    end = content.find("---", 3)
    if end == -1:
        return ""
    frontmatter = content[3:end]
    for line in frontmatter.splitlines():
        if line.startswith("description:"):
            return line[len("description:") :].strip()
    return ""


def _esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
