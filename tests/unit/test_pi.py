from __future__ import annotations

import json

import pytest

from tea.agent.agent_run import AgentRun
from tea.agent.pi import (
    Pi,
    PiConfig,
    PiHarness,
    _build_models_json,
    _read_skill_description,
)
from tea.executor import RawResult

_ANTHROPIC_CFG = PiConfig(
    "anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY"
)

# ── build_spec ────────────────────────────────────────────────────────────────


def test_build_spec_defaults_no_base_url(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    spec = Pi(_ANTHROPIC_CFG).build_spec("hello", timeout=60)

    assert spec.timeout == 60
    assert not spec.requirements.host_network_access
    assert spec.requirements.config_scopes == []
    assert spec.setup_command is None
    assert "--model anthropic/claude-sonnet-4-6" in spec.command


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
    spec = Pi(PiConfig("foo/bar", api_key_env="MISSING_KEY")).build_spec(
        "hi", timeout=30
    )
    assert "MISSING_KEY" not in spec.env


def test_build_spec_with_base_url_writes_models_json(monkeypatch):
    monkeypatch.setenv("PROVIDER_KEY", "sk-cloud-xyz")
    cfg = PiConfig(
        "ollama/qwen2.5-coder:1.5b",
        api_key_env="PROVIDER_KEY",
        base_url="https://ollama.example/v1",
    )
    spec = Pi(cfg).build_spec("hi", timeout=30)

    assert spec.requirements.host_network_access is True
    assert len(spec.requirements.config_scopes) == 1
    scope = spec.requirements.config_scopes[0]
    assert scope.env_var == "PI_CODING_AGENT_DIR"
    models_json = scope.files["models.json"]
    assert '"apiKey": "sk-cloud-xyz"' in models_json
    assert '"baseUrl": "https://ollama.example/v1"' in models_json


def test_build_spec_with_base_url_but_no_api_key_env_uses_local(monkeypatch):
    cfg = PiConfig(
        "ollama/qwen2.5-coder:1.5b", base_url="http://host.docker.internal:11434/v1"
    )
    spec = Pi(cfg).build_spec("hi", timeout=30)
    scope = spec.requirements.config_scopes[0]
    assert '"apiKey": "local"' in scope.files["models.json"]


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
    new = PiHarness().with_model(PiConfig("ollama/x", base_url="http://h/v1"))
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
