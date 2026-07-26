from __future__ import annotations

import json
import logging
import os
import shlex
from dataclasses import dataclass, replace

import yaml

from tea.executor import (
    WORKDIR_MOUNT,
    ExecutionRequirements,
    ExecutionSpec,
    RawResult,
)
from tea.executor.docker_executor import DockerExecutor, DockerProfile

from ._utils import _sanitize_env_value
from ._version import resolve_cli_version
from .agent import Agent
from .agent_run import AgentRun, Step, StepType, ToolCall
from .harness import Harness

_log = logging.getLogger(__name__)

_NODE_VERSION = "22"
_PI_PACKAGE = "@earendil-works/pi-coding-agent"
_PI_VERSION_ENV = "PI_VERSION"
_CONTAINER_HOME = "/home/node"
_NPM_PREFIX = f"{_CONTAINER_HOME}/.npm-global"

_PI_AGENT_DIR = f"{_CONTAINER_HOME}/.pi/agent"
# Where Pi auto-discovers user-level skills inside the container — see
# https://pi.dev/docs/latest/skills (directories containing SKILL.md are
# scanned recursively).
_PI_NATIVE_SKILLS_DIR = f"{_PI_AGENT_DIR}/skills"


def _resolve_version() -> str:
    return resolve_cli_version("pi --version", _PI_PACKAGE, _PI_VERSION_ENV)


def _dockerfile(version: str) -> str:
    return (
        f"FROM node:{_NODE_VERSION}\n"
        f"ENV NPM_CONFIG_PREFIX={_NPM_PREFIX}\n"
        f"RUN npm install -g {_PI_PACKAGE}@{version} --quiet 2>/dev/null\n"
    )


def pi_docker_profile(agent: Pi) -> DockerProfile:
    """Static Docker knowledge for Pi, resolved lazily (see ClaudeCode)."""
    version = agent.version()
    return DockerProfile(
        image=f"tea-pi:{version}",
        dockerfile=_dockerfile(version),
        user="node",
    )


@dataclass
class PiConfig:
    """Pi-specific model configuration.

    model:       "provider/model-id" string (e.g. "anthropic/claude-sonnet-4-6")
    api_key_env: name of the host env var to forward into the container
    base_url:    OpenAI-compatible endpoint — only needed for non-native
                 providers (Ollama, vLLM, LM Studio). Native cloud providers
                 (Anthropic, OpenAI, Gemini, …) are known to Pi already.

                 The URL is used verbatim inside the container, so a provider
                 listening on the host must be named the way the container
                 sees it: under ``DockerExecutor`` that is
                 ``http://host.docker.internal:11434/v1``, not ``localhost``
                 (which resolves to the container itself). Setting ``base_url``
                 declares ``host_network_access``, which is what makes that
                 name resolve — but the rewrite itself is still the caller's
                 job. See https://github.com/rsn491/tea/issues/52.
    """

    model: str
    api_key_env: str | None = None
    base_url: str | None = None


class Pi(Agent):
    DEFAULT_SKILL_SOURCES = (".pi/skills", ".agents/skills")

    def __init__(self, model_config: PiConfig) -> None:
        self._model_config = model_config

    def build_spec(self, prompt: str, timeout: int) -> ExecutionSpec:
        # The environment the pi CLI itself needs, independent of who runs it:
        # any executor handed this spec must set it, so it belongs here rather
        # than in a Docker profile.
        env: dict[str, str] = {
            "HOME": _CONTAINER_HOME,
            "NPM_CONFIG_PREFIX": _NPM_PREFIX,
            # Skip pi's startup network operations (update/registry checks) —
            # they add latency and flakiness; model calls are unaffected.
            "PI_OFFLINE": "1",
        }
        api_key: str | None = None
        if self._model_config.api_key_env:
            if key := os.environ.get(self._model_config.api_key_env):
                env[self._model_config.api_key_env] = key
                api_key = key

        requirements = ExecutionRequirements()
        setup_command: str | None = None

        if self._model_config.base_url:
            # Write a Pi models.json so Pi knows how to reach the custom
            # provider. The model string must be "provider/model-id"; we derive
            # the provider name from the part before the first slash
            # (e.g. "ollama").
            models_json = _build_models_json(
                self._model_config.model,
                self._model_config.base_url,
                api_key,
            )
            escaped = models_json.replace("'", "'\\''")
            setup_command = (
                f"mkdir -p {_PI_AGENT_DIR}"
                f" && printf '%s' '{escaped}' > {_PI_AGENT_DIR}/models.json"
            )
            # A local provider (Ollama, vLLM, LM Studio) listens on the host;
            # the executor decides how to make the host reachable.
            requirements = ExecutionRequirements(host_network_access=True)

        env["PI_PROMPT"] = _sanitize_env_value(prompt)

        return ExecutionSpec(
            command=(
                f"{_NPM_PREFIX}/bin/pi --mode json --no-extensions --print"
                f" --model {shlex.quote(self._model_config.model)}"
                ' "$PI_PROMPT"'
            ),
            setup_command=setup_command,
            env=env,
            timeout=timeout,
            requirements=requirements,
        )

    def install_skills(
        self,
        spec: ExecutionSpec,
        prompt: str,
        workdir: str,
        skills: list[str],
        source_for: dict[str, str],
    ) -> tuple[ExecutionSpec, str]:
        """Copy project skills into Pi's native discovery path.

        Pi auto-discovers skills from ``~/.pi/agent/skills/<name>/SKILL.md``
        at startup. The workdir is mounted at ``/workspace``, so each skill
        directory is copied from its discovered source via a setup command
        and the prompt is returned unmodified.
        """
        if not skills:
            return spec, prompt
        for name in skills:
            _warn_if_pi_skips_name(name)
            _warn_if_missing_description(
                os.path.join(workdir, source_for[name], name, "SKILL.md")
            )
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
        # Pi's JSON print mode exits 0 even when the model call fails (a dead
        # endpoint, bad key, or DNS failure yields message_end events with
        # stopReason="error" and empty content, then exit 0). Surface that
        # through the channels consumers actually check so a failed run is not
        # mistaken for a quiet success.
        if run.error and run.exit_code == 0:
            run.exit_code = 1
            if not run.stderr:
                run.stderr = run.error
        return run


class PiHarness:
    """Factory for Pi runs.

    Exposes only ``with_model()``: Pi has no default model and no OAuth/api-key
    fallback path, so a ``PiConfig`` must always be supplied externally.
    Because ``PiHarness`` does not inherit ``Harness``, ``Agents.Pi.prompt(...)``
    is a static type error — the only valid entry point is
    ``Agents.Pi.with_model(config).prompt(...)``.
    """

    def __init__(self, *, skills_sources: list[str] | None = None) -> None:
        self._skills_sources = (
            list(skills_sources) if skills_sources is not None else None
        )

    def with_model(self, config: PiConfig) -> Harness:
        agent = Pi(model_config=config)
        return Harness(
            agent,
            DockerExecutor(lambda: pi_docker_profile(agent)),
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
    # Tracks the failure state of the most recent assistant turn. A later
    # successful turn (e.g. after a retry) clears it, so only a run whose final
    # assistant message errored is reported as failed.
    last_error: str | None = None

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
            if message.get("stopReason") in ("error", "aborted"):
                last_error = (
                    message.get("errorMessage")
                    or f"pi stopReason={message.get('stopReason')}"
                )
            else:
                last_error = None
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            steps.append(
                                Step(type=StepType.TEXT, content=text, raw=event)
                            )
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
            steps.append(
                Step(type=StepType.TOOL_USE, content=json.dumps(args), raw=event)
            )

        elif event_type == "tool_execution_end":
            result = event.get("result")
            if isinstance(result, dict):
                content = json.dumps(result)
            elif result is not None:
                content = str(result)
            else:
                content = ""
            steps.append(Step(type=StepType.TOOL_RESULT, content=content, raw=event))

    return AgentRun(raw=stdout, steps=steps, tools=tools, skills=[], error=last_error)


def _skill_setup(skills: list[str], source_for: dict[str, str]) -> str:
    """Build the shell prelude that installs skills into Pi's native path.

    Copies each ``/workspace/<source_for[name]>/<name>/`` directory (mounted
    workdir) into ``~/.pi/agent/skills/`` so Pi auto-discovers the skills at
    startup. The whole directory is copied, not just ``SKILL.md``: Pi tells
    the model to resolve relative paths in a skill against the skill
    directory, so supporting files must travel with it.
    """
    cmds = [f"mkdir -p {_PI_NATIVE_SKILLS_DIR}"]
    for name in skills:
        # shlex.quote protects the shell word but not the path: a name like
        # "../evil" would still be interpreted as a path traversal once the
        # shell strips the quotes. Reject any name containing a path separator.
        if "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"Invalid skill name: {name!r}")
        quoted = shlex.quote(name)
        src_base = f"{WORKDIR_MOUNT}/{source_for[name]}"
        src = f"{shlex.quote(src_base)}/{quoted}"
        cmds.append(f"cp -R {src} {_PI_NATIVE_SKILLS_DIR}/")
    return " && ".join(cmds)


def _warn_if_pi_skips_name(name: str) -> None:
    """Warn when Pi's discovery will silently skip a copied skill directory.

    Pi's skill scanner ignores directory entries whose name starts with ``.``
    or is exactly ``node_modules`` (see dist/core/skills.js). Such a skill is
    copied into the native path but never advertised to the model and produces
    no diagnostic, so surface it on the host.
    """
    if name.startswith(".") or name == "node_modules":
        _log.warning(
            "skill %r will be silently skipped by Pi (it ignores dot-prefixed "
            "and node_modules directories); the model will not see it",
            name,
        )


def _warn_if_missing_description(skill_md_path: str) -> None:
    """Warn when a SKILL.md lacks the frontmatter description Pi requires.

    Pi parses the frontmatter as YAML and silently drops any skill whose
    parsed ``description`` is missing or empty, or whose frontmatter fails to
    parse at all (it emits only a startup diagnostic inside the container),
    which is painful to debug from outside. Mirror that accept/drop logic here
    with a real YAML parse so the host warning matches Pi's actual behavior.
    """
    try:
        with open(skill_md_path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return
    frontmatter = _extract_frontmatter(content)
    reason: str | None = None
    if frontmatter is None:
        reason = "has no YAML frontmatter block"
    else:
        try:
            data = yaml.safe_load(frontmatter)
        except yaml.YAMLError:
            reason = "has frontmatter that is not valid YAML"
        else:
            description = ""
            if isinstance(data, dict):
                description = str(data.get("description") or "").strip()
            if not description:
                reason = "has no frontmatter 'description'"
    if reason is not None:
        _log.warning(
            "SKILL.md at %s %s; Pi will silently ignore this skill",
            skill_md_path,
            reason,
        )


def _extract_frontmatter(content: str) -> str | None:
    """Return the YAML frontmatter block, or None if absent."""
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 3)
    if end == -1:
        return None
    return content[3:end]
