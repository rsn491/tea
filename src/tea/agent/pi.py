from __future__ import annotations

import json
import os

from tea.executor import DockerSpec, RawResult
from tea.executor.docker_executor import DockerExecutor

from ._utils import _esc
from ._version import resolve_cli_version
from .agent import Agent
from .agent_run import AgentRun, Step, StepType, ToolCall
from .harness import Harness
from .model_config import ModelConfig

_NODE_VERSION = "22"
_PI_PACKAGE = "pi"
_PI_VERSION_ENV = "PI_VERSION"


class Pi(Agent):
    DEFAULT_SKILL_SOURCES = (".pi/skills", ".agents/skills")

    def __init__(self, model_config: ModelConfig) -> None:
        self._model_config = model_config

    def build_spec(self, prompt: str, timeout: int) -> DockerSpec:
        npm_prefix = "/home/node/.npm-global"
        env: dict[str, str] = {"HOME": "/home/node", "NPM_CONFIG_PREFIX": npm_prefix}
        api_key: str | None = None
        if self._model_config.api_key_env:
            if key := os.environ.get(self._model_config.api_key_env):
                env[self._model_config.api_key_env] = key
                api_key = key

        extra_hosts: dict[str, str] = {}
        setup_command: str | None = None

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
            setup_command = (
                f"mkdir -p /home/node/.pi/agent"
                f" && printf '%s' '{escaped}' > /home/node/.pi/agent/models.json"
            )
            extra_hosts["host.docker.internal"] = "host-gateway"

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

    def install_skills(
        self,
        spec: DockerSpec,
        prompt: str,
        workdir: str,
        skills: list[str],
        source_for: dict[str, str],
    ) -> tuple[DockerSpec, str]:
        """Prepend a skill listing to the prompt — Pi has no native skill loader.

        Reads each ``SKILL.md``'s frontmatter ``description`` from the host
        workdir so the agent sees titles, descriptions, and the in-container
        relative paths it can read on demand. Each path in the preamble is
        relative to the container cwd (``/workspace``) and reflects the source
        the skill was discovered in.
        """
        entries = []
        for name in skills:
            src_dir = source_for[name]
            skill_path = os.path.join(workdir, src_dir, name, "SKILL.md")
            description = _read_skill_description(skill_path)
            rel_path = f"{src_dir}/{name}/SKILL.md"
            entries.append(f"- {name}: {description}\n  Path: {rel_path}")
        if not entries:
            return spec, prompt
        listing = "\n".join(entries)
        preamble = (
            "The following project skills are available to guide your work. "
            "If a skill is relevant to your task, read it at the provided path "
            "and follow its guidance.\n\n"
            f"Available skills:\n{listing}"
        )
        return spec, f"{preamble}\n\n{prompt}"

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

    def __init__(self, *, skills_sources: list[str] | None = None) -> None:
        self._skills_sources = (
            list(skills_sources) if skills_sources is not None else None
        )

    def with_model(self, config: ModelConfig) -> Harness:
        return Harness(
            Pi(model_config=config),
            DockerExecutor(),
            skills_sources=self._skills_sources,
        )


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
                            steps.append(Step(type=StepType.TEXT, content=text, raw=event))
            elif isinstance(content, str) and content:
                steps.append(Step(type=StepType.TEXT, content=content, raw=event))

        elif event_type == "tool_execution_start":
            tool_name = event.get("toolName", "")
            tool_call_id = event.get("toolCallId", "")
            args = event.get("args", {})
            if not isinstance(args, dict):
                args = {}
            tc = ToolCall(name=tool_name, input=args, tool_use_id=tool_call_id)
            tools.append(tc)
            steps.append(Step(type=StepType.TOOL_USE, content=json.dumps(args), raw=event))

        elif event_type == "tool_execution_end":
            result = event.get("result")
            if isinstance(result, dict):
                content = json.dumps(result)
            elif result is not None:
                content = str(result)
            else:
                content = ""
            steps.append(Step(type=StepType.TOOL_RESULT, content=content, raw=event))

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


