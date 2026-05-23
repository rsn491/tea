from __future__ import annotations

import json
import re
from datetime import date

import pytest

from tea.agent._version import resolve_cli_version
from tea.agent.agent_run import AgentRun
from tea.agent.model_config import ModelConfig
from tea.agent.pi import (
    Pi,
    PiHarness,
    _build_models_json,
    _read_skill_description,
)
from tea.executor import RawResult

_ANTHROPIC_CFG = ModelConfig(
    "anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY"
)

# ── resolve_cli_version ───────────────────────────────────────────────────────


def test_resolve_cli_version_uses_env_var(monkeypatch):
    monkeypatch.setenv("PI_VERSION", "3.2.1")
    resolve_cli_version.cache_clear()
    assert resolve_cli_version("pi", "pi", "PI_VERSION") == "3.2.1"
    resolve_cli_version.cache_clear()


def test_resolve_cli_version_last_resort_is_latest_date(monkeypatch):
    """When env var, CLI, and npm all fail the version is latest-<yyyyMMdd>."""
    monkeypatch.delenv("PI_VERSION", raising=False)
    resolve_cli_version.cache_clear()
    # Use a nonsense CLI name so both the CLI and npm fallback fail
    version = resolve_cli_version("__no_such_cli__", "__no_such_pkg__", "PI_VERSION")
    expected = f"latest-{date.today().strftime('%Y%m%d')}"
    assert version == expected
    resolve_cli_version.cache_clear()


def test_pi_agent_version_uses_env_var(monkeypatch):
    """Pi.version() delegates to resolve_cli_version and picks up the env var."""
    monkeypatch.setenv("PI_VERSION", "9.8.7")
    resolve_cli_version.cache_clear()
    assert Pi(_ANTHROPIC_CFG).version() == "9.8.7"
    resolve_cli_version.cache_clear()


# ── build_spec ────────────────────────────────────────────────────────────────


def test_build_spec_defaults_no_base_url(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("PI_VERSION", "1.0.0")
    resolve_cli_version.cache_clear()
    spec = Pi(_ANTHROPIC_CFG).build_spec("hello", timeout=60)

    assert spec.image == "tea-pi:1.0.0"
    assert spec.user == "node"
    assert spec.timeout == 60
    assert spec.extra_hosts == {}
    assert spec.setup_command is None
    assert "FROM node:22" in spec.dockerfile
    assert "pi@1.0.0" in spec.dockerfile
    assert "--model anthropic/claude-sonnet-4-6" in spec.command
    resolve_cli_version.cache_clear()


def test_build_spec_forwards_api_key_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-host-abc")
    spec = Pi(_ANTHROPIC_CFG).build_spec("hello", timeout=60)
    assert spec.env["ANTHROPIC_API_KEY"] == "sk-host-abc"


def test_build_spec_no_api_key_env_when_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    spec = Pi(_ANTHROPIC_CFG).build_spec("hello", timeout=60)
    assert "ANTHROPIC_API_KEY" not in spec.env


def test_build_spec_api_key_env_set_but_missing_from_environ(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    spec = Pi(ModelConfig("foo/bar", api_key_env="MISSING_KEY")).build_spec(
        "hi", timeout=30
    )
    assert "MISSING_KEY" not in spec.env


def test_build_spec_with_base_url_writes_models_json(monkeypatch):
    monkeypatch.setenv("PROVIDER_KEY", "sk-cloud-xyz")
    cfg = ModelConfig(
        "ollama/qwen2.5-coder:1.5b",
        api_key_env="PROVIDER_KEY",
        base_url="https://ollama.example/v1",
    )
    spec = Pi(cfg).build_spec("hi", timeout=30)

    assert spec.extra_hosts == {"host.docker.internal": "host-gateway"}
    assert "mkdir -p /home/node/.pi/agent" in spec.setup_command
    assert "models.json" in spec.setup_command
    # the resolved key from the host env should be baked into the models.json
    # written to the container — find it inside the printf payload.
    assert '"apiKey": "sk-cloud-xyz"' in spec.setup_command
    assert '"baseUrl": "https://ollama.example/v1"' in spec.setup_command
    assert "models.json" in spec.setup_command


def test_build_spec_with_base_url_but_no_api_key_env_uses_local(monkeypatch):
    cfg = ModelConfig(
        "ollama/qwen2.5-coder:1.5b", base_url="http://host.docker.internal:11434/v1"
    )
    spec = Pi(cfg).build_spec("hi", timeout=30)
    assert '"apiKey": "local"' in spec.setup_command


# ── _build_models_json ────────────────────────────────────────────────────────


def test_build_models_json_provider_split():
    raw = _build_models_json("ollama/qwen2.5", "http://x/v1", None)
    cfg = json.loads(raw)
    assert "ollama" in cfg["providers"]
    provider = cfg["providers"]["ollama"]
    assert provider["baseUrl"] == "http://x/v1"
    assert provider["models"] == [{"id": "qwen2.5"}]
    assert provider["api"] == "openai-completions"


def test_build_models_json_no_slash_falls_back_to_custom():
    raw = _build_models_json("plainmodel", "http://x/v1", None)
    cfg = json.loads(raw)
    assert "custom" in cfg["providers"]
    assert cfg["providers"]["custom"]["models"] == [{"id": "plainmodel"}]


def test_build_models_json_uses_resolved_api_key():
    raw = _build_models_json("foo/bar", "http://x/v1", "sk-resolved")
    assert json.loads(raw)["providers"]["foo"]["apiKey"] == "sk-resolved"


def test_build_models_json_defaults_to_local_when_no_key():
    raw = _build_models_json("foo/bar", "http://x/v1", None)
    assert json.loads(raw)["providers"]["foo"]["apiKey"] == "local"


# ── PiHarness ─────────────────────────────────────────────────────────────────


def test_pi_harness_with_model_threads_config_through():
    new = PiHarness().with_model(ModelConfig("ollama/x", base_url="http://h/v1"))
    inner = new._agent  # type: ignore[attr-defined]
    assert isinstance(inner, Pi)
    assert inner._model_config.model == "ollama/x"
    assert inner._model_config.base_url == "http://h/v1"


def test_pi_harness_has_no_prompt_method():
    # Pi has no default model: Agents.Pi.prompt(...) must be a type error and
    # an AttributeError at runtime. This guards against accidental regression
    # to a Harness-subclass shape that would silently inherit `.prompt()`.
    assert not hasattr(PiHarness(), "prompt")


# ── Pi.parse wrapper ──────────────────────────────────────────────────────────


def test_pi_parse_attaches_exit_code_stderr_and_duration():
    stdout = json.dumps(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
            },
        }
    )
    raw = RawResult(stdout=stdout, stderr="warn", exit_code=2, duration_s=1.25)
    run = Pi(_ANTHROPIC_CFG).parse(raw)

    assert isinstance(run, AgentRun)
    assert run.exit_code == 2
    assert run.stderr == "warn"
    assert run.duration_s == pytest.approx(1.25)
    assert len(run.steps) == 1
    assert run.steps[0].content == "ok"


# ── _read_skill_description ───────────────────────────────────────────────────


def test_read_skill_description_parses_frontmatter(tmp_path):
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\ndescription: Add a new math operation\n---\n# body\n")
    assert _read_skill_description(str(skill)) == "Add a new math operation"


def test_read_skill_description_missing_file():
    assert _read_skill_description("/nonexistent/SKILL.md") == ""


def test_read_skill_description_no_frontmatter(tmp_path):
    skill = tmp_path / "SKILL.md"
    skill.write_text("# No frontmatter here\n")
    assert _read_skill_description(str(skill)) == ""


def test_read_skill_description_no_description_key(tmp_path):
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\ntitle: Something\n---\n")
    assert _read_skill_description(str(skill)) == ""


# ── Pi.prepare_skills ─────────────────────────────────────────────────────────


def test_prepare_skills_prepends_listing(tmp_path):
    skills_dir = tmp_path / ".claude" / "skills" / "add-operation"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\ndescription: How to add an operation\n---\n# body\n"
    )
    result = Pi(_ANTHROPIC_CFG).prepare_skills(
        "Do the task", str(tmp_path), ["add-operation"]
    )
    assert "Available skills:" in result
    assert "add-operation: How to add an operation" in result
    assert ".claude/skills/add-operation/SKILL.md" in result
    assert result.endswith("Do the task")


def test_prepare_skills_no_skills_returns_prompt_unchanged():
    result = Pi(_ANTHROPIC_CFG).prepare_skills("Do the task", "/some/dir", [])
    assert result == "Do the task"


def test_prepare_skills_multiple_skills(tmp_path):
    for name, desc in [("skill-a", "First skill"), ("skill-b", "Second skill")]:
        d = tmp_path / ".claude" / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\ndescription: {desc}\n---\n")
    result = Pi(_ANTHROPIC_CFG).prepare_skills(
        "Task", str(tmp_path), ["skill-a", "skill-b"]
    )
    assert "skill-a: First skill" in result
    assert "skill-b: Second skill" in result
