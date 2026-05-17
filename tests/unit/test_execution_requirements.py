"""Tests for harness-specific configs and ExecutionRequirements."""

from __future__ import annotations

import os
from unittest.mock import patch

from tea.agent import Agents
from tea.agent.claude_code import ClaudeCode, ClaudeCodeHarness
from tea.agent.codex import Codex
from tea.agent.harness import Harness
from tea.agent.pi import Pi, PiConfig, PiHarness
from tea.executor import DockerSpec, ExecutionRequirements
from tea.executor.docker import DockerExecutor
from tea.infra import DockerRunConfig

# ── ExecutionRequirements defaults ───────────────────────────────────────────


def test_execution_requirements_defaults():
    req = ExecutionRequirements()
    assert req.host_network_access is False
    assert req.extra_mounts == {}


def test_execution_requirements_custom():
    req = ExecutionRequirements(host_network_access=True, extra_mounts={"/a": "/b"})
    assert req.host_network_access is True
    assert req.extra_mounts == {"/a": "/b"}


# ── DockerExecutor translates requirements ────────────────────────────────────


def test_docker_executor_host_network_access_adds_extra_hosts():
    spec = DockerSpec(
        command="echo hi",
        image="node:22",
        requirements=ExecutionRequirements(host_network_access=True),
    )
    captured: list[DockerRunConfig] = []

    from tea.infra import DockerRunResult

    def fake_run(cfg: DockerRunConfig):
        captured.append(cfg)
        return DockerRunResult(stdout="", stderr="", exit_code=0)

    with patch("tea.executor.docker.run_in_docker", side_effect=fake_run):
        DockerExecutor().run(spec, workdir=None)

    assert captured[0].extra_hosts == {"host.docker.internal": "host-gateway"}


def test_docker_executor_no_host_network_no_extra_hosts():
    spec = DockerSpec(
        command="echo hi",
        image="node:22",
        requirements=ExecutionRequirements(host_network_access=False),
    )
    captured: list[DockerRunConfig] = []

    from tea.infra import DockerRunResult

    def fake_run(cfg: DockerRunConfig):
        captured.append(cfg)
        return DockerRunResult(stdout="", stderr="", exit_code=0)

    with patch("tea.executor.docker.run_in_docker", side_effect=fake_run):
        DockerExecutor().run(spec, workdir=None)

    assert captured[0].extra_hosts == {}


def test_docker_executor_extra_mounts_become_volumes():
    spec = DockerSpec(
        command="echo hi",
        image="node:22",
        requirements=ExecutionRequirements(
            extra_mounts={"/host/claude": "/cont/claude"}
        ),
    )
    captured: list[DockerRunConfig] = []

    from tea.infra import DockerRunResult

    def fake_run(cfg: DockerRunConfig):
        captured.append(cfg)
        return DockerRunResult(stdout="", stderr="", exit_code=0)

    with patch("tea.executor.docker.run_in_docker", side_effect=fake_run):
        DockerExecutor().run(spec, workdir=None)

    assert "/host/claude" in captured[0].volumes
    assert captured[0].volumes["/host/claude"] == "/cont/claude"


# ── Pi uses requirements, not extra_hosts ────────────────────────────────────


def test_pi_build_spec_uses_requirements_not_extra_hosts():
    cfg = PiConfig(
        "ollama/qwen2.5-coder:1.5b", base_url="http://host.docker.internal:11434/v1"
    )
    spec = Pi(cfg).build_spec("hello", timeout=60)
    assert spec.requirements.host_network_access is True
    assert not hasattr(spec, "extra_hosts")  # field was removed


def test_pi_build_spec_no_base_url_no_host_network():
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    spec = Pi(cfg).build_spec("hello", timeout=60)
    assert spec.requirements.host_network_access is False


# ── ClaudeCode uses requirements, not extra_volumes ──────────────────────────


def test_claude_code_build_spec_uses_requirements_not_extra_volumes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(os.path, "isdir", lambda p: True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path))
    (tmp_path).mkdir(parents=True, exist_ok=True)
    spec = ClaudeCode().build_spec("hello", timeout=60)
    assert str(tmp_path) in spec.requirements.extra_mounts
    assert not hasattr(spec, "extra_volumes")  # field was removed


# ── PiConfig type ─────────────────────────────────────────────────────────────


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


def test_pi_harness_accepts_pi_config():
    cfg = PiConfig("ollama/qwen2.5-coder:1.5b", base_url="http://x/v1")
    harness = PiHarness().with_model(cfg)
    assert isinstance(harness, Harness)
    assert isinstance(harness._agent, Pi)
    assert isinstance(harness._agent._model_config, PiConfig)


# ── ClaudeCode with_model(str) ────────────────────────────────────────────────


def test_claude_code_harness_with_model_returns_harness():
    harness = Agents.ClaudeCode.with_model("claude-opus-4-7")
    assert isinstance(harness, Harness)


def test_claude_code_harness_with_model_sets_model():
    harness = Agents.ClaudeCode.with_model("claude-opus-4-7")
    agent = harness._agent
    assert isinstance(agent, ClaudeCode)
    assert agent._model == "claude-opus-4-7"


def test_claude_code_harness_with_model_preserves_max_turns():
    base = ClaudeCodeHarness(ClaudeCode(max_turns=5), DockerExecutor())
    harness = base.with_model("claude-opus-4-7")
    agent = harness._agent
    assert isinstance(agent, ClaudeCode)
    assert agent._max_turns == 5


# ── Codex with_model(str) ────────────────────────────────────────────────────


def test_codex_harness_with_model_returns_harness():
    harness = Agents.Codex.with_model("gpt-5.3-codex")
    assert isinstance(harness, Harness)


def test_codex_harness_with_model_sets_model():
    harness = Agents.Codex.with_model("gpt-5.3-codex")
    agent = harness._agent
    assert isinstance(agent, Codex)
    assert agent._model == "gpt-5.3-codex"


# ── Agents catalog ────────────────────────────────────────────────────────────


def test_agents_pi_has_no_prompt():
    assert not hasattr(Agents.Pi, "prompt")


def test_agents_pi_with_model_accepts_pi_config():
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    harness = Agents.Pi.with_model(cfg)
    assert isinstance(harness, Harness)
