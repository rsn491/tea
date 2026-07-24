"""Tests for ExecutionRequirements, ConfigScope, DockerProfile, and DockerExecutor."""

from __future__ import annotations

import os

import pytest

from tea.agent import Agents
from tea.agent._version import resolve_cli_version
from tea.agent.claude_code import ClaudeCode, ClaudeCodeHarness, _claude_docker_profile
from tea.agent.codex import Codex, _codex_docker_profile
from tea.agent.harness import Harness
from tea.agent.pi import Pi, PiConfig, PiHarness
from tea.executor import ConfigScope, ExecutionRequirements, ExecutionSpec
from tea.executor.docker_executor import DockerExecutor, DockerProfile
from tea.infra import DockerRunConfig, DockerRunResult


class _FakeDocker:
    """Stands in for tea.infra.Docker; records configs, returns empty results."""

    def __init__(self) -> None:
        self.configs: list[DockerRunConfig] = []
        self.images: list[tuple[str, str]] = []
        self.scope_files: dict[str, str] = {}

    def create_image(self, tag: str, dockerfile: str) -> None:
        self.images.append((tag, dockerfile))

    def run(self, config: DockerRunConfig) -> DockerRunResult:
        self.configs.append(config)
        # Snapshot scope-file contents while the host tmp dirs still exist.
        for host_path, container_path in config.volumes.items():
            if not container_path.startswith("/tmp/tea-scope-"):
                continue
            for root, _dirs, files in os.walk(host_path):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, host_path)
                    with open(fpath, encoding="utf-8") as fh:
                        self.scope_files[rel] = fh.read()
        return DockerRunResult(stdout="", stderr="", exit_code=0)


def _run(profile: DockerProfile, spec: ExecutionSpec, workdir: str | None = None):
    fake = _FakeDocker()
    DockerExecutor(profile, docker=fake).run(spec, workdir)
    return fake


# ── ExecutionRequirements defaults ───────────────────────────────────────────


def test_execution_requirements_defaults():
    req = ExecutionRequirements()
    assert req.host_network_access is False
    assert req.config_scopes == []
    assert req.extra_mounts == {}


# ── DockerProfile ─────────────────────────────────────────────────────────────


def test_docker_profile_defaults():
    p = DockerProfile(image="node:22")
    assert p.dockerfile is None
    assert p.user is None
    assert p.setup_command is None
    assert p.env_overrides == {}


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
    resolve_cli_version.cache_clear()
    profile = _claude_docker_profile()

    assert profile.image == "tea-claude-code:1.2.3"
    assert profile.user == "node"
    assert "FROM node:22" in profile.dockerfile
    assert "@anthropic-ai/claude-code@1.2.3" in profile.dockerfile
    assert profile.env_overrides["HOME"] == "/home/node"
    resolve_cli_version.cache_clear()


def test_claude_code_agent_version_uses_env_var(monkeypatch):
    """ClaudeCode.version() delegates to resolve_cli_version."""
    monkeypatch.setenv("CLAUDE_CODE_VERSION", "9.8.7")
    resolve_cli_version.cache_clear()
    assert ClaudeCode().version() == "9.8.7"
    resolve_cli_version.cache_clear()


def test_codex_docker_profile_pins_versioned_image(monkeypatch):
    monkeypatch.setenv("CODEX_VERSION", "4.5.6")
    resolve_cli_version.cache_clear()
    profile = _codex_docker_profile()

    assert profile.image == "tea-codex:4.5.6"
    assert profile.user == "node"
    assert "FROM node:22" in profile.dockerfile
    assert "@openai/codex@4.5.6" in profile.dockerfile
    assert profile.env_overrides["HOME"] == "/home/node"
    resolve_cli_version.cache_clear()


def test_codex_agent_version_uses_env_var(monkeypatch):
    """Codex.version() delegates to resolve_cli_version."""
    monkeypatch.setenv("CODEX_VERSION", "9.8.7")
    resolve_cli_version.cache_clear()
    assert Codex().version() == "9.8.7"
    resolve_cli_version.cache_clear()


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


# ── ConfigScope materialisation ──────────────────────────────────────────────


def _scoped_spec(*scopes: ConfigScope) -> ExecutionSpec:
    return ExecutionSpec(
        command="run", requirements=ExecutionRequirements(config_scopes=list(scopes))
    )


def test_config_scope_sets_env_var_to_container_path():
    spec = _scoped_spec(
        ConfigScope(env_var="PI_CODING_AGENT_DIR", files={"models.json": "{}"})
    )
    fake = _run(DockerProfile(image="node:22"), spec)
    assert fake.configs[0].env["PI_CODING_AGENT_DIR"] == "/tmp/tea-scope-0"


def test_config_scope_mounts_host_tmp_at_container_path():
    spec = _scoped_spec(ConfigScope(env_var="MY_DIR", files={"f.txt": "content"}))
    fake = _run(DockerProfile(image="node:22"), spec)
    assert "/tmp/tea-scope-0" in fake.configs[0].volumes.values()


def test_config_scope_files_written_before_container_runs():
    spec = _scoped_spec(
        ConfigScope(env_var="MY_DIR", files={"settings.json": '{"ok": true}'})
    )
    fake = _run(DockerProfile(image="node:22"), spec)
    assert fake.scope_files["settings.json"] == '{"ok": true}'


def test_config_scope_nested_file_paths():
    spec = _scoped_spec(ConfigScope(env_var="D", files={"sub/dir/f.json": "{}"}))
    fake = _run(DockerProfile(image="node:22"), spec)
    assert fake.scope_files[os.path.join("sub", "dir", "f.json")] == "{}"


def test_config_scope_rejects_path_escape():
    spec = _scoped_spec(ConfigScope(env_var="D", files={"../evil.txt": "x"}))
    fake = _FakeDocker()
    with pytest.raises(ValueError, match="escapes its scope directory"):
        DockerExecutor(DockerProfile(image="node:22"), docker=fake).run(spec, None)
    assert fake.configs == []  # nothing ran


def test_config_scope_multiple_scopes_get_sequential_paths():
    spec = _scoped_spec(
        ConfigScope(env_var="DIR_A", files={"a.json": "{}"}),
        ConfigScope(env_var="DIR_B", files={"b.json": "{}"}),
    )
    fake = _run(DockerProfile(image="node:22"), spec)
    assert fake.configs[0].env["DIR_A"] == "/tmp/tea-scope-0"
    assert fake.configs[0].env["DIR_B"] == "/tmp/tea-scope-1"


def test_config_scope_tmp_dirs_cleaned_up_after_run():
    spec = _scoped_spec(ConfigScope(env_var="MY_DIR", files={"f.txt": "x"}))
    fake = _run(DockerProfile(image="node:22"), spec)
    host_dirs = [
        host
        for host, ctr in fake.configs[0].volumes.items()
        if ctr.startswith("/tmp/tea-scope-")
    ]
    assert host_dirs, "expected a scope mount"
    for path in host_dirs:
        assert not os.path.exists(path), f"tmp dir {path} was not cleaned up"


def test_config_scope_tmp_dirs_cleaned_up_when_run_raises():
    class _ExplodingDocker(_FakeDocker):
        def run(self, config: DockerRunConfig) -> DockerRunResult:
            super().run(config)
            raise RuntimeError("boom")

    spec = _scoped_spec(ConfigScope(env_var="MY_DIR", files={"f.txt": "x"}))
    fake = _ExplodingDocker()
    with pytest.raises(RuntimeError, match="boom"):
        DockerExecutor(DockerProfile(image="node:22"), docker=fake).run(spec, None)
    host_dirs = [
        host
        for host, ctr in fake.configs[0].volumes.items()
        if ctr.startswith("/tmp/tea-scope-")
    ]
    for path in host_dirs:
        assert not os.path.exists(path), f"tmp dir {path} leaked after failure"


# ── setup_command sequencing ──────────────────────────────────────────────────


def test_profile_setup_runs_before_spec_setup():
    profile = DockerProfile(image="node:22", setup_command="profile-setup")
    spec = ExecutionSpec(command="main-cmd", setup_command="spec-setup")
    fake = _run(profile, spec)
    assert fake.configs[0].command[2] == "profile-setup && spec-setup && main-cmd"


def test_only_profile_setup_no_spec_setup():
    profile = DockerProfile(image="node:22", setup_command="install-stuff")
    fake = _run(profile, ExecutionSpec(command="main-cmd"))
    assert fake.configs[0].command[2] == "install-stuff && main-cmd"


def test_no_setup_runs_command_directly():
    fake = _run(DockerProfile(image="node:22"), ExecutionSpec(command="main-cmd"))
    assert fake.configs[0].command == ["sh", "-c", "main-cmd"]


# ── Pi uses config_scopes ─────────────────────────────────────────────────────


def test_pi_ollama_uses_config_scope_for_models_json():
    cfg = PiConfig(
        "ollama/qwen2.5-coder:1.5b", base_url="http://host.docker.internal:11434/v1"
    )
    spec = Pi(cfg).build_spec("hello", timeout=60)

    assert spec.requirements.host_network_access is True
    assert len(spec.requirements.config_scopes) == 1
    scope = spec.requirements.config_scopes[0]
    assert scope.env_var == "PI_CODING_AGENT_DIR"
    assert "models.json" in scope.files
    assert '"baseUrl"' in scope.files["models.json"]


def test_pi_no_base_url_no_requirements():
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    spec = Pi(cfg).build_spec("hello", timeout=60)
    assert spec.requirements.host_network_access is False
    assert spec.requirements.config_scopes == []


def test_pi_skills_follow_relocated_agent_dir():
    """When a ConfigScope moves Pi's agent dir, skill installs must follow it —
    a fixed /home/node/.pi/agent/skills copy would be invisible to Pi."""
    cfg = PiConfig("ollama/q", base_url="http://h/v1")
    base = Pi(cfg).build_spec("task", timeout=60)
    spec, _ = Pi(cfg).install_skills(base, "task", "/tmp/x", ["s"], {"s": "skills"})
    assert (
        'cp -R /workspace/skills/s "${PI_CODING_AGENT_DIR:-/home/node/.pi/agent}"'
        "/skills/"
    ) in spec.setup_command


# ── ClaudeCode requirements ──────────────────────────────────────────────────


def test_claude_code_has_no_requirements(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    spec = ClaudeCode().build_spec("hello", timeout=60)
    assert spec.requirements.host_network_access is False
    assert spec.requirements.config_scopes == []
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
    base = ClaudeCodeHarness(
        ClaudeCode(max_turns=5), DockerExecutor(_claude_docker_profile)
    )
    harness = base.with_model("claude-opus-4-7")
    assert isinstance(harness._agent, ClaudeCode)
    assert harness._agent.max_turns == 5


def test_claude_code_harness_with_model_preserves_skills_sources():
    base = ClaudeCodeHarness(
        ClaudeCode(),
        DockerExecutor(_claude_docker_profile),
        skills_sources=["eval/skills"],
    )
    harness = base.with_model("claude-opus-4-7")
    assert harness.skills_sources == ["eval/skills"]


# ── Codex with_model ──────────────────────────────────────────────────────────


def test_codex_harness_with_model_sets_model():
    harness = Agents.Codex.with_model("gpt-5.3-codex")
    assert isinstance(harness, Harness)
    assert isinstance(harness._agent, Codex)
    assert harness._agent.model == "gpt-5.3-codex"


# ── Agents catalog ────────────────────────────────────────────────────────────


def test_agents_pi_has_no_prompt():
    assert not hasattr(Agents.Pi, "prompt")


def test_agents_pi_with_model_accepts_pi_config():
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    harness = Agents.Pi.with_model(cfg)
    assert isinstance(harness, Harness)
