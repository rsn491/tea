"""Tests for ExecutionRequirements, DockerProfile, and DockerExecutor."""

from __future__ import annotations

import pytest

import tea.executor
from tea.agent import Agents
from tea.agent.claude_code import ClaudeCode, ClaudeCodeHarness, claude_docker_profile
from tea.agent.harness import Harness
from tea.agent.pi import Pi, PiConfig, PiHarness
from tea.executor import ExecutionRequirements, ExecutionSpec
from tea.executor.docker_executor import DockerExecutor, DockerProfile
from tea.infra import DockerRunConfig, DockerRunResult


class _FakeDocker:
    """Stands in for tea.infra.Docker; records configs, returns empty results."""

    def __init__(self) -> None:
        self.configs: list[DockerRunConfig] = []
        self.images: list[tuple[str, str]] = []

    def create_image(self, tag: str, dockerfile: str) -> None:
        self.images.append((tag, dockerfile))

    def run(self, config: DockerRunConfig) -> DockerRunResult:
        self.configs.append(config)
        return DockerRunResult(stdout="", stderr="", exit_code=0)


def _run(profile: DockerProfile, spec: ExecutionSpec, workdir: str | None = None):
    fake = _FakeDocker()
    DockerExecutor(profile, docker=fake).run(spec, workdir)
    return fake


# ── ExecutionRequirements defaults ───────────────────────────────────────────


def test_execution_requirements_defaults():
    req = ExecutionRequirements()
    assert req.host_network_access is False
    assert req.extra_mounts == {}


# ── DockerProfile ─────────────────────────────────────────────────────────────


def test_docker_profile_defaults():
    p = DockerProfile(image="node:22")
    assert p.dockerfile is None
    assert p.user is None
    assert p.env_overrides == {}


def test_docker_profile_rejects_empty_image():
    """An empty tag must fail here, not reach ``docker run``."""
    with pytest.raises(ValueError, match="non-empty image tag"):
        DockerProfile(image="")


def test_docker_profile_env_overrides_applied():
    profile = DockerProfile(image="node:22", env_overrides={"HOME": "/home/node"})
    spec = ExecutionSpec(command="echo hi", env={"MY_KEY": "val"})
    fake = _run(profile, spec)
    assert fake.configs[0].env["HOME"] == "/home/node"
    assert fake.configs[0].env["MY_KEY"] == "val"


def test_spec_env_overrides_profile_env():
    profile = DockerProfile(image="node:22", env_overrides={"KEY": "from_profile"})
    spec = ExecutionSpec(command="echo hi", env={"KEY": "from_spec"})
    fake = _run(profile, spec)
    assert fake.configs[0].env["KEY"] == "from_spec"


def test_docker_profile_dockerfile_triggers_image_build():
    profile = DockerProfile(image="tea-x:1.0.0", dockerfile="FROM node:22\n")
    fake = _run(profile, ExecutionSpec(command="run"))
    assert fake.images == [("tea-x:1.0.0", "FROM node:22\n")]


def test_docker_profile_no_dockerfile_no_image_build():
    fake = _run(DockerProfile(image="node:22"), ExecutionSpec(command="run"))
    assert fake.images == []


def test_docker_executor_accepts_profile_factory():
    """A zero-arg callable is resolved lazily at run time, not at construction."""
    calls: list[int] = []

    def factory() -> DockerProfile:
        calls.append(1)
        return DockerProfile(image="node:22", user="node")

    fake = _FakeDocker()
    executor = DockerExecutor(factory, docker=fake)
    assert calls == []  # not resolved yet
    executor.run(ExecutionSpec(command="echo hi"), workdir=None)
    assert calls == [1]
    assert fake.configs[0].image == "node:22"
    assert fake.configs[0].user == "node"


# ── Agent DockerProfile factories ────────────────────────────────────────────
#
# Each agent ships a zero-arg factory holding its static Docker knowledge. The
# CLI version is resolved at call time and pins both the image tag and the
# Dockerfile's npm install, so a version bump forces a fresh build instead of
# silently reusing a stale image.


def test_claude_docker_profile_pins_versioned_image(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_VERSION", "1.2.3")
    profile = claude_docker_profile()

    assert profile.image == "tea-claude-code:1.2.3"
    assert profile.user == "node"
    assert "FROM node:22" in profile.dockerfile
    assert "@anthropic-ai/claude-code@1.2.3" in profile.dockerfile
    assert profile.env_overrides["HOME"] == "/home/node"


def test_claude_code_agent_version_uses_env_var(monkeypatch):
    """ClaudeCode.version() delegates to resolve_cli_version."""
    monkeypatch.setenv("CLAUDE_CODE_VERSION", "9.8.7")
    assert ClaudeCode().version() == "9.8.7"


# ── host_network_access ───────────────────────────────────────────────────────


def test_host_network_access_adds_extra_hosts():
    spec = ExecutionSpec(
        command="echo hi",
        requirements=ExecutionRequirements(host_network_access=True),
    )
    fake = _run(DockerProfile(image="node:22"), spec)
    assert fake.configs[0].extra_hosts == {"host.docker.internal": "host-gateway"}


def test_no_host_network_no_extra_hosts():
    fake = _run(DockerProfile(image="node:22"), ExecutionSpec(command="echo hi"))
    assert fake.configs[0].extra_hosts == {}


# ── extra_mounts ──────────────────────────────────────────────────────────────


def test_extra_mounts_added_to_volumes(tmp_path):
    spec = ExecutionSpec(
        command="run",
        requirements=ExecutionRequirements(
            extra_mounts={str(tmp_path): "/container/extra"}
        ),
    )
    fake = _run(DockerProfile(image="node:22"), spec)
    assert fake.configs[0].volumes[str(tmp_path)] == "/container/extra"


# ── setup_command sequencing ──────────────────────────────────────────────────


def test_spec_setup_runs_before_command():
    spec = ExecutionSpec(command="main-cmd", setup_command="spec-setup")
    fake = _run(DockerProfile(image="node:22"), spec)
    assert fake.configs[0].command[2] == "spec-setup && main-cmd"


def test_no_setup_runs_command_directly():
    fake = _run(DockerProfile(image="node:22"), ExecutionSpec(command="main-cmd"))
    assert fake.configs[0].command == ["sh", "-c", "main-cmd"]


# ── Pi declares requirements ──────────────────────────────────────────────────


def test_pi_ollama_declares_host_network_access():
    cfg = PiConfig(
        "ollama/qwen2.5-coder:1.5b", base_url="http://host.docker.internal:11434/v1"
    )
    spec = Pi(cfg).build_spec("hello", timeout=60)

    assert spec.requirements.host_network_access is True
    # The agent no longer names host.docker.internal itself — the executor does.
    assert "models.json" in spec.setup_command


def test_pi_no_base_url_no_requirements():
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    spec = Pi(cfg).build_spec("hello", timeout=60)
    assert spec.requirements.host_network_access is False
    assert spec.requirements.extra_mounts == {}


# ── ClaudeCode requirements ──────────────────────────────────────────────────


def test_claude_code_has_no_requirements(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    spec = ClaudeCode().build_spec("hello", timeout=60)
    assert spec.requirements.host_network_access is False
    assert spec.requirements.extra_mounts == {}
    assert spec.setup_command is None


# ── PiConfig ──────────────────────────────────────────────────────────────────


def test_pi_config_fields():
    cfg = PiConfig(
        "ollama/qwen2.5-coder:1.5b", api_key_env="MY_KEY", base_url="http://x/v1"
    )
    assert cfg.model == "ollama/qwen2.5-coder:1.5b"
    assert cfg.api_key_env == "MY_KEY"
    assert cfg.base_url == "http://x/v1"


def test_pi_config_defaults():
    cfg = PiConfig("anthropic/claude-sonnet-4-6")
    assert cfg.api_key_env is None
    assert cfg.base_url is None


def test_pi_harness_with_model_returns_harness():
    cfg = PiConfig("ollama/qwen2.5-coder:1.5b", base_url="http://x/v1")
    harness = PiHarness().with_model(cfg)
    assert isinstance(harness, Harness)
    assert isinstance(harness._agent, Pi)


# ── ClaudeCode with_model ─────────────────────────────────────────────────────


def test_claude_code_harness_with_model_sets_model():
    harness = Agents.ClaudeCode.with_model("claude-opus-4-7")
    assert isinstance(harness, Harness)
    assert isinstance(harness._agent, ClaudeCode)
    assert harness._agent.model == "claude-opus-4-7"


def test_claude_code_harness_with_model_preserves_max_turns():
    base = ClaudeCodeHarness.docker(ClaudeCode(max_turns=5))
    harness = base.with_model("claude-opus-4-7")
    assert isinstance(harness._agent, ClaudeCode)
    assert harness._agent.max_turns == 5


def test_claude_code_harness_with_model_preserves_skills_sources():
    base = ClaudeCodeHarness.docker(skills_sources=["eval/skills"])
    harness = base.with_model("claude-opus-4-7")
    assert harness.skills_sources == ["eval/skills"]


def test_claude_code_harness_with_model_preserves_extra_volumes():
    """Every agent field survives the rebuild, not just the ones named."""
    base = ClaudeCodeHarness.docker(ClaudeCode(extra_volumes={"/host": "/container"}))
    harness = base.with_model("claude-opus-4-7")
    spec = harness._agent.build_spec("hi", timeout=30)
    assert spec.requirements.extra_mounts == {"/host": "/container"}


def test_claude_code_factories_compose():
    """Both factories return the concrete harness, so they chain either way."""
    harness = (
        ClaudeCodeHarness.docker(ClaudeCode(max_turns=7)).with_model("m").with_api_key()
    )
    assert isinstance(harness, ClaudeCodeHarness)
    assert isinstance(harness._agent, ClaudeCode)
    assert harness._agent.model == "m"
    assert harness._agent.max_turns == 7


# ── Agent ↔ image pairing ─────────────────────────────────────────────────────


def test_docker_factories_pair_each_agent_with_its_own_image(monkeypatch):
    """``.docker()`` is the single wiring point; each one picks its own image."""
    monkeypatch.setenv("CLAUDE_CODE_VERSION", "1.2.3")
    monkeypatch.setenv("PI_VERSION", "4.5.6")

    claude = ClaudeCodeHarness.docker()._executor._profile()
    pi = PiHarness().with_model(PiConfig("ollama/x"))._executor._profile()

    assert claude.image == "tea-claude-code:1.2.3"
    assert pi.image == "tea-pi:4.5.6"


# ── tea.executor stays Docker-free ────────────────────────────────────────────


def test_executor_package_exposes_no_docker_symbols():
    """The executor-agnostic layer must not re-export a concrete executor.

    ``tea.executor`` re-exporting ``DockerProfile`` made the abstract types
    unreachable without ``tea.executor.docker_executor`` — and so without the
    Docker SDK — which is precisely what the abstraction exists to avoid. Both
    Docker types are importable from ``tea.executor.docker_executor`` only.

    (Loading them out-of-process to prove the SDK is never imported is not
    possible: ``import tea.executor`` first executes ``tea/__init__.py``, the
    convenience namespace, which deliberately eager-imports everything.)
    """
    assert "DockerProfile" not in tea.executor.__all__
    assert "DockerExecutor" not in tea.executor.__all__
    assert not hasattr(tea.executor, "DockerProfile")
    assert not hasattr(tea.executor, "DockerExecutor")


# ── Agents catalog ────────────────────────────────────────────────────────────


def test_agents_pi_has_no_prompt():
    assert not hasattr(Agents.Pi, "prompt")


def test_agents_pi_with_model_accepts_pi_config():
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    harness = Agents.Pi.with_model(cfg)
    assert isinstance(harness, Harness)
