"""Tests for ExecutionRequirements, ConfigScope, DockerProfile, and DockerExecutor."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

from tea.agent import Agents
from tea.agent.claude_code import _CLAUDE_DOCKER_PROFILE, ClaudeCode, ClaudeCodeHarness
from tea.agent.codex import Codex
from tea.agent.harness import Harness
from tea.agent.pi import Pi, PiConfig, PiHarness
from tea.executor import ConfigScope, ExecutionRequirements, ExecutionSpec
from tea.executor.docker import DockerExecutor, DockerProfile
from tea.infra import DockerRunConfig, DockerRunResult


def _fake_run(captured: list[DockerRunConfig]):
    def _run(cfg: DockerRunConfig):
        captured.append(cfg)
        return DockerRunResult(stdout="", stderr="", exit_code=0)

    return _run


# ── ExecutionRequirements defaults ───────────────────────────────────────────


def test_execution_requirements_defaults():
    req = ExecutionRequirements()
    assert req.host_network_access is False
    assert req.config_scopes == []


def test_execution_requirements_with_config_scope():
    scope = ConfigScope(env_var="MY_DIR", files={"cfg.json": "{}"})
    req = ExecutionRequirements(config_scopes=[scope])
    assert len(req.config_scopes) == 1
    assert req.config_scopes[0].env_var == "MY_DIR"


# ── DockerProfile ─────────────────────────────────────────────────────────────


def test_docker_profile_defaults():
    p = DockerProfile(image="node:22")
    assert p.user is None
    assert p.setup_command is None
    assert p.env_overrides == {}


def test_docker_profile_env_overrides_applied():
    profile = DockerProfile(image="node:22", env_overrides={"HOME": "/home/node"})
    spec = ExecutionSpec(command="echo hi", env={"MY_KEY": "val"})
    captured: list[DockerRunConfig] = []

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run(captured)):
        DockerExecutor(profile).run(spec, workdir=None)

    assert captured[0].env["HOME"] == "/home/node"
    assert captured[0].env["MY_KEY"] == "val"


def test_spec_env_overrides_profile_env():
    profile = DockerProfile(image="node:22", env_overrides={"KEY": "from_profile"})
    spec = ExecutionSpec(command="echo hi", env={"KEY": "from_spec"})
    captured: list[DockerRunConfig] = []

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run(captured)):
        DockerExecutor(profile).run(spec, workdir=None)

    assert captured[0].env["KEY"] == "from_spec"


# ── host_network_access ───────────────────────────────────────────────────────


def test_docker_executor_host_network_access_adds_extra_hosts():
    spec = ExecutionSpec(
        command="echo hi",
        requirements=ExecutionRequirements(host_network_access=True),
    )
    captured: list[DockerRunConfig] = []

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run(captured)):
        DockerExecutor(DockerProfile(image="node:22")).run(spec, workdir=None)

    assert captured[0].extra_hosts == {"host.docker.internal": "host-gateway"}


def test_docker_executor_no_host_network_no_extra_hosts():
    spec = ExecutionSpec(command="echo hi")
    captured: list[DockerRunConfig] = []

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run(captured)):
        DockerExecutor(DockerProfile(image="node:22")).run(spec, workdir=None)

    assert captured[0].extra_hosts == {}


# ── ConfigScope materialisation ──────────────────────────────────────────────


def test_config_scope_sets_env_var_to_container_path():
    scope = ConfigScope(env_var="PI_CODING_AGENT_DIR", files={"models.json": "{}"})
    spec = ExecutionSpec(
        command="pi run",
        requirements=ExecutionRequirements(config_scopes=[scope]),
    )
    captured: list[DockerRunConfig] = []

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run(captured)):
        DockerExecutor(DockerProfile(image="node:22")).run(spec, workdir=None)

    assert captured[0].env["PI_CODING_AGENT_DIR"] == "/tmp/tea-scope-0"


def test_config_scope_mounts_host_tmp_at_container_path():
    scope = ConfigScope(env_var="MY_DIR", files={"f.txt": "content"})
    spec = ExecutionSpec(
        command="run",
        requirements=ExecutionRequirements(config_scopes=[scope]),
    )
    captured: list[DockerRunConfig] = []

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run(captured)):
        DockerExecutor(DockerProfile(image="node:22")).run(spec, workdir=None)

    assert "/tmp/tea-scope-0" in captured[0].volumes.values()


def test_config_scope_files_written_before_container_runs():
    written: dict[str, str] = {}
    scope = ConfigScope(env_var="MY_DIR", files={"settings.json": '{"ok": true}'})
    spec = ExecutionSpec(
        command="run",
        requirements=ExecutionRequirements(config_scopes=[scope]),
    )

    def capturing_run(cfg: DockerRunConfig):
        for host_path, cpath in cfg.volumes.items():
            if cpath == "/tmp/tea-scope-0":
                f = os.path.join(host_path, "settings.json")
                if os.path.exists(f):
                    with open(f) as fh:
                        written["settings.json"] = fh.read()
        return DockerRunResult(stdout="", stderr="", exit_code=0)

    with patch("tea.executor.docker.run_in_docker", side_effect=capturing_run):
        DockerExecutor(DockerProfile(image="node:22")).run(spec, workdir=None)

    assert written["settings.json"] == '{"ok": true}'


def test_config_scope_multiple_scopes_get_sequential_paths():
    spec = ExecutionSpec(
        command="run",
        requirements=ExecutionRequirements(
            config_scopes=[
                ConfigScope(env_var="DIR_A", files={"a.json": "{}"}),
                ConfigScope(env_var="DIR_B", files={"b.json": "{}"}),
            ]
        ),
    )
    captured: list[DockerRunConfig] = []

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run(captured)):
        DockerExecutor(DockerProfile(image="node:22")).run(spec, workdir=None)

    assert captured[0].env["DIR_A"] == "/tmp/tea-scope-0"
    assert captured[0].env["DIR_B"] == "/tmp/tea-scope-1"


def test_config_scope_tmp_dir_cleaned_up_after_run(tmp_path):
    created_tmps: list[str] = []
    original_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(**kwargs):
        path = original_mkdtemp(**kwargs)
        created_tmps.append(path)
        return path

    scope = ConfigScope(env_var="MY_DIR", files={"f.txt": "x"})
    spec = ExecutionSpec(
        command="run",
        requirements=ExecutionRequirements(config_scopes=[scope]),
    )

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run([])):
        with patch(
            "tea.executor.docker.tempfile.mkdtemp", side_effect=tracking_mkdtemp
        ):
            DockerExecutor(DockerProfile(image="node:22")).run(spec, workdir=None)

    for path in created_tmps:
        assert not os.path.exists(path), f"tmp dir {path} was not cleaned up"


# ── setup_command sequencing ──────────────────────────────────────────────────


def test_profile_setup_runs_before_spec_setup():
    profile = DockerProfile(image="node:22", setup_command="profile-setup")
    spec = ExecutionSpec(command="main-cmd", setup_command="spec-setup")
    captured: list[DockerRunConfig] = []

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run(captured)):
        DockerExecutor(profile).run(spec, workdir=None)

    shell_cmd = captured[0].command[2]
    assert shell_cmd == "profile-setup && spec-setup && main-cmd"


def test_only_profile_setup_no_spec_setup():
    profile = DockerProfile(image="node:22", setup_command="install-stuff")
    spec = ExecutionSpec(command="main-cmd")
    captured: list[DockerRunConfig] = []

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run(captured)):
        DockerExecutor(profile).run(spec, workdir=None)

    assert captured[0].command[2] == "install-stuff && main-cmd"


def test_no_setup_runs_command_directly():
    spec = ExecutionSpec(command="main-cmd")
    captured: list[DockerRunConfig] = []

    with patch("tea.executor.docker.run_in_docker", side_effect=_fake_run(captured)):
        DockerExecutor(DockerProfile(image="node:22")).run(spec, workdir=None)

    assert captured[0].command == ["sh", "-c", "main-cmd"]


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


def test_pi_no_base_url_no_config_scopes():
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    spec = Pi(cfg).build_spec("hello", timeout=60)
    assert spec.requirements.host_network_access is False
    assert spec.requirements.config_scopes == []


# ── ClaudeCode has no requirements ───────────────────────────────────────────


def test_claude_code_has_no_requirements():
    spec = ClaudeCode().build_spec("hello", timeout=60)
    assert spec.requirements.host_network_access is False
    assert spec.requirements.config_scopes == []
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


def test_claude_code_harness_with_model_returns_harness():
    harness = Agents.ClaudeCode.with_model("claude-opus-4-7")
    assert isinstance(harness, Harness)


def test_claude_code_harness_with_model_sets_model():
    harness = Agents.ClaudeCode.with_model("claude-opus-4-7")
    assert isinstance(harness._agent, ClaudeCode)
    assert harness._agent._model == "claude-opus-4-7"


def test_claude_code_harness_with_model_preserves_max_turns():
    base = ClaudeCodeHarness(
        ClaudeCode(max_turns=5), DockerExecutor(_CLAUDE_DOCKER_PROFILE)
    )
    harness = base.with_model("claude-opus-4-7")
    assert isinstance(harness._agent, ClaudeCode)
    assert harness._agent._max_turns == 5


# ── Codex with_model ──────────────────────────────────────────────────────────


def test_codex_harness_with_model_returns_harness():
    harness = Agents.Codex.with_model("gpt-5.3-codex")
    assert isinstance(harness, Harness)


def test_codex_harness_with_model_sets_model():
    harness = Agents.Codex.with_model("gpt-5.3-codex")
    assert isinstance(harness._agent, Codex)
    assert harness._agent._model == "gpt-5.3-codex"


# ── Agents catalog ────────────────────────────────────────────────────────────


def test_agents_pi_has_no_prompt():
    assert not hasattr(Agents.Pi, "prompt")


def test_agents_pi_with_model_accepts_pi_config():
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    harness = Agents.Pi.with_model(cfg)
    assert isinstance(harness, Harness)
