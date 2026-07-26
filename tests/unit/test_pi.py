from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest

from tea.agent._version import resolve_cli_version
from tea.agent.agent_run import AgentRun
from tea.agent.pi import (
    Pi,
    PiConfig,
    PiHarness,
    _build_models_json,
    pi_docker_profile,
)
from tea.executor import ExecutionSpec, RawResult

_ANTHROPIC_CFG = PiConfig(
    "anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY"
)

# ── resolve_cli_version ───────────────────────────────────────────────────────


def test_resolve_cli_version_uses_env_var(monkeypatch):
    monkeypatch.setenv("PI_VERSION", "3.2.1")
    assert resolve_cli_version("pi --version", "pi", "PI_VERSION") == "3.2.1"


def test_resolve_cli_version_last_resort_is_latest_date(monkeypatch):
    """When env var, CLI, and npm all fail the version is latest-<yyyyMMdd>."""
    monkeypatch.delenv("PI_VERSION", raising=False)
    # Simulate a host with no CLI and no npm at all — keeps the test hermetic
    # (the npm-view fallback would otherwise do a live registry round-trip).
    monkeypatch.setattr(
        "tea.agent._version.subprocess.run",
        lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()),
    )
    version = resolve_cli_version(
        "__no_such_cli__ --version", "__no_such_pkg__", "PI_VERSION"
    )
    expected = f"latest-{date.today().strftime('%Y%m%d')}"
    assert version == expected


def test_resolve_cli_version_npm_list_scoped_package(monkeypatch):
    """The npm-list fallback parses the version off a scoped package line.

    A scoped name contains an '@', so the version must be the part after the
    *last* '@' — e.g. '@earendil-works/pi-coding-agent@1.2.3' -> '1.2.3'.
    """
    monkeypatch.delenv("PI_VERSION", raising=False)
    pkg = "@earendil-works/pi-coding-agent"

    def fake_run(cmd, **kwargs):
        class R:
            stdout = ""

        if cmd[0] == "npm" and cmd[1] == "list":
            R.stdout = f"/home/x\n└── {pkg}@1.2.3\n"
            return R
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr("tea.agent._version.subprocess.run", fake_run)
    assert resolve_cli_version("__no_cli__ --version", pkg, "PI_VERSION") == "1.2.3"


def test_resolve_cli_version_npm_view_fallback(monkeypatch):
    """With no CLI and no global install, the npm registry version is used."""
    monkeypatch.delenv("PI_VERSION", raising=False)

    def fake_run(cmd, **kwargs):
        class R:
            stdout = ""

        if cmd[0] == "npm" and cmd[1] == "view":
            R.stdout = "9.9.9\n"
            return R
        if cmd[0] == "npm":
            return R
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr("tea.agent._version.subprocess.run", fake_run)
    version = resolve_cli_version(
        "__no_such_cli__ --version", "@scope/some-pkg", "PI_VERSION"
    )
    assert version == "9.9.9"


def test_pi_agent_version_uses_env_var(monkeypatch):
    """Pi.version() delegates to resolve_cli_version and picks up the env var."""
    monkeypatch.setenv("PI_VERSION", "9.8.7")
    assert Pi(_ANTHROPIC_CFG).version() == "9.8.7"


# ── build_spec ────────────────────────────────────────────────────────────────


def test_docker_profile_pins_versioned_image(monkeypatch):
    monkeypatch.setenv("PI_VERSION", "1.0.0")
    profile = pi_docker_profile(Pi(_ANTHROPIC_CFG))

    assert profile.image == "tea-pi:1.0.0"
    assert profile.user == "node"
    assert "FROM node:22" in profile.dockerfile
    assert "@earendil-works/pi-coding-agent@1.0.0" in profile.dockerfile


def test_build_spec_defaults_no_base_url(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    spec = Pi(_ANTHROPIC_CFG).build_spec("hello", timeout=60)

    assert spec.timeout == 60
    assert spec.requirements.host_network_access is False
    assert spec.setup_command is None
    # The env the pi CLI needs travels with the spec, so it survives being
    # handed to any executor — not just the one carrying a DockerProfile.
    assert spec.env["HOME"] == "/home/node"
    assert spec.env["NPM_CONFIG_PREFIX"] == "/home/node/.npm-global"
    assert spec.env["PI_OFFLINE"] == "1"
    assert "--model anthropic/claude-sonnet-4-6" in spec.command
    # These flags are load-bearing: without --print pi opens a TUI and exits
    # silently; without --mode json parse() finds no events and returns empty
    # steps; --no-extensions keeps startup deterministic.
    assert "--print" in spec.command
    assert "--mode json" in spec.command
    assert "--no-extensions" in spec.command


def test_build_spec_model_injection_is_quoted(monkeypatch):
    """A hostile model string must not break out of the pi command line."""
    monkeypatch.setenv("PI_VERSION", "1.0.0")
    cfg = PiConfig("ollama/qwen; touch /tmp/PWNED")
    spec = Pi(cfg).build_spec("hello", timeout=60)
    assert "--model 'ollama/qwen; touch /tmp/PWNED'" in spec.command
    sanitised = spec.command.replace("'ollama/qwen; touch /tmp/PWNED'", "SAFE")
    assert "touch /tmp/PWNED" not in sanitised


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

    # The agent declares the need for host access; the executor decides how.
    assert spec.requirements.host_network_access is True
    assert "mkdir -p /home/node/.pi/agent" in spec.setup_command
    assert "models.json" in spec.setup_command
    # the resolved key from the host env should be baked into the models.json
    # written to the container — find it inside the printf payload.
    assert '"apiKey": "sk-cloud-xyz"' in spec.setup_command
    assert '"baseUrl": "https://ollama.example/v1"' in spec.setup_command


def test_build_spec_with_base_url_but_no_api_key_env_uses_local(monkeypatch):
    cfg = PiConfig(
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
    assert run.error is None


def _assistant_end(*, stop_reason="stop", text="", error_message=None):
    message = {"role": "assistant", "stopReason": stop_reason, "content": []}
    if text:
        message["content"] = [{"type": "text", "text": text}]
    if error_message is not None:
        message["errorMessage"] = error_message
    return json.dumps({"type": "message_end", "message": message})


def test_pi_parse_surfaces_model_error_as_nonzero_exit():
    """pi json mode exits 0 on model failure; the harness must not report success."""
    stdout = "\n".join(
        _assistant_end(stop_reason="error", error_message="Connection error.")
        for _ in range(4)
    )
    raw = RawResult(stdout=stdout, stderr="", exit_code=0, duration_s=0.5)
    run = Pi(_ANTHROPIC_CFG).parse(raw)

    assert run.error == "Connection error."
    assert run.exit_code == 1, "a failed model call must surface as nonzero exit"
    assert run.stderr == "Connection error."
    assert run.steps == []


def test_pi_parse_error_then_success_is_not_flagged():
    """A retry that eventually succeeds is a successful run, not a failure."""
    stdout = "\n".join(
        [
            _assistant_end(stop_reason="error", error_message="Connection error."),
            _assistant_end(stop_reason="stop", text="recovered"),
        ]
    )
    raw = RawResult(stdout=stdout, stderr="", exit_code=0, duration_s=0.5)
    run = Pi(_ANTHROPIC_CFG).parse(raw)

    assert run.error is None
    assert run.exit_code == 0
    assert [s.content for s in run.steps] == ["recovered"]


def test_pi_parse_error_does_not_override_real_nonzero_exit():
    """A genuine container exit code is preserved, not clobbered to 1."""
    stdout = _assistant_end(stop_reason="error", error_message="boom")
    raw = RawResult(stdout=stdout, stderr="real stderr", exit_code=137, duration_s=0.1)
    run = Pi(_ANTHROPIC_CFG).parse(raw)

    assert run.error == "boom"
    assert run.exit_code == 137
    assert run.stderr == "real stderr"


# ── Pi.install_skills ─────────────────────────────────────────────────────────


def _empty_spec() -> ExecutionSpec:
    return ExecutionSpec(command="noop")


def test_install_skills_copies_into_pi_native_path():
    """Pi auto-discovers skills from ~/.pi/agent/skills/<name>/SKILL.md."""
    spec, prompt = Pi(_ANTHROPIC_CFG).install_skills(
        _empty_spec(),
        "Do the task",
        "/tmp/anywhere",
        ["add-operation"],
        {"add-operation": "skills"},
    )
    assert prompt == "Do the task"  # Pi doesn't touch the prompt
    assert spec.setup_command is not None
    assert "mkdir -p /home/node/.pi/agent/skills" in spec.setup_command
    assert "cp -R /workspace/skills/add-operation /home/node/.pi/agent/skills/" in (
        spec.setup_command
    )


def test_install_skills_reflects_per_skill_source():
    """Pi copies each skill from its own discovered source directory."""
    spec, _ = Pi(_ANTHROPIC_CFG).install_skills(
        _empty_spec(),
        "Task",
        "/tmp/x",
        ["alpha", "beta"],
        {"alpha": ".pi/skills", "beta": ".agents/skills"},
    )
    # Pin the exact name-to-source pairing, not just substring presence — a
    # swapped mapping would otherwise still contain both source strings.
    assert (
        "cp -R /workspace/.pi/skills/alpha /home/node/.pi/agent/skills/"
        in spec.setup_command
    )
    assert "cp -R /workspace/.agents/skills/beta /home/node/.pi/agent/skills/" in (
        spec.setup_command
    )


def test_install_skills_no_skills_returns_prompt_unchanged():
    spec = _empty_spec()
    out_spec, prompt = Pi(_ANTHROPIC_CFG).install_skills(
        spec, "Do the task", "/some/dir", [], {}
    )
    assert out_spec is spec
    assert prompt == "Do the task"


def test_install_skills_multiple_skills():
    spec, _ = Pi(_ANTHROPIC_CFG).install_skills(
        _empty_spec(),
        "Task",
        "/tmp/x",
        ["skill-a", "skill-b"],
        {"skill-a": "skills", "skill-b": "skills"},
    )
    assert (
        "cp -R /workspace/skills/skill-a /home/node/.pi/agent/skills/"
        in spec.setup_command
    )
    assert (
        "cp -R /workspace/skills/skill-b /home/node/.pi/agent/skills/"
        in spec.setup_command
    )


def test_install_skills_preserves_existing_setup():
    """If the spec already carries setup, install_skills chains, not replaces."""
    base = replace(_empty_spec(), setup_command="echo prelude")
    spec, _ = Pi(_ANTHROPIC_CFG).install_skills(
        base, "Task", "/tmp/x", ["s"], {"s": "skills"}
    )
    assert spec.setup_command.startswith("echo prelude && ")
    assert (
        "cp -R /workspace/skills/s /home/node/.pi/agent/skills/" in spec.setup_command
    )


def test_install_skills_chains_with_models_json_setup():
    """End-to-end: build_spec sets models.json, install_skills appends skill copies."""
    cfg = PiConfig("ollama/qwen", base_url="http://host.docker.internal:11434/v1")
    base = Pi(cfg).build_spec("Task", timeout=60)
    assert "models.json" in base.setup_command  # precondition

    spec, _ = Pi(cfg).install_skills(base, "Task", "/tmp/x", ["s"], {"s": "skills"})
    assert "models.json" in spec.setup_command
    skill_cp = "cp -R /workspace/skills/s /home/node/.pi/agent/skills/"
    assert skill_cp in spec.setup_command
    assert spec.setup_command.index("models.json") < spec.setup_command.index(skill_cp)


def test_install_skills_warns_when_description_missing(tmp_path, caplog):
    """Pi silently drops skills without a frontmatter description; the harness
    must surface that on the host at install time."""
    skill_dir = tmp_path / "skills" / "greet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# greet\nJust a body, no frontmatter.\n")

    with caplog.at_level("WARNING", logger="tea.agent.pi"):
        Pi(_ANTHROPIC_CFG).install_skills(
            _empty_spec(), "Task", str(tmp_path), ["greet"], {"greet": "skills"}
        )
    assert any("silently ignore this skill" in r.message for r in caplog.records)


def test_install_skills_no_warning_with_description(tmp_path, caplog):
    skill_dir = tmp_path / "skills" / "greet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: greet\ndescription: How to greet.\n---\n# greet\n"
    )

    with caplog.at_level("WARNING", logger="tea.agent.pi"):
        Pi(_ANTHROPIC_CFG).install_skills(
            _empty_spec(), "Task", str(tmp_path), ["greet"], {"greet": "skills"}
        )
    assert not caplog.records


@pytest.mark.parametrize(
    "frontmatter",
    [
        'description: ""',  # empty quoted string — pi's YAML parse drops it
        "description: How to: greet",  # unquoted colon — YAML parse error
        "name: greet",  # description key absent entirely
    ],
)
def test_install_skills_warns_on_pi_droppable_description(
    tmp_path, caplog, frontmatter
):
    """The host warning must match Pi's real YAML accept/drop behavior, not a
    naive line match."""
    skill_dir = tmp_path / "skills" / "greet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n# greet\n")

    with caplog.at_level("WARNING", logger="tea.agent.pi"):
        Pi(_ANTHROPIC_CFG).install_skills(
            _empty_spec(), "Task", str(tmp_path), ["greet"], {"greet": "skills"}
        )
    assert any("silently ignore this skill" in r.message for r in caplog.records)


def test_install_skills_warns_on_unterminated_frontmatter(tmp_path, caplog):
    """A frontmatter block that opens with '---' but never closes is not valid
    frontmatter to Pi, so the skill is dropped — warn on it."""
    skill_dir = tmp_path / "skills" / "greet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\ndescription: greet\n# greet body\n")

    with caplog.at_level("WARNING", logger="tea.agent.pi"):
        Pi(_ANTHROPIC_CFG).install_skills(
            _empty_spec(), "Task", str(tmp_path), ["greet"], {"greet": "skills"}
        )
    assert any("silently ignore this skill" in r.message for r in caplog.records)


def test_install_skills_warns_on_dot_prefixed_name(tmp_path, caplog):
    """Pi skips dot-prefixed skill dirs; the harness must surface that."""
    skill_dir = tmp_path / "skills" / ".internal"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\ndescription: hidden.\n---\n# x\n")

    with caplog.at_level("WARNING", logger="tea.agent.pi"):
        Pi(_ANTHROPIC_CFG).install_skills(
            _empty_spec(), "Task", str(tmp_path), [".internal"], {".internal": "skills"}
        )
    assert any("silently skipped by Pi" in r.message for r in caplog.records)


@pytest.mark.parametrize("bad_name", ["../evil", "a/b", "..", ".", "a\\b"])
def test_install_skills_rejects_path_traversal(bad_name):
    with pytest.raises(ValueError, match="Invalid skill name"):
        Pi(_ANTHROPIC_CFG).install_skills(
            _empty_spec(), "Task", "/tmp/x", [bad_name], {bad_name: "skills"}
        )


def test_install_skills_skill_name_injection_is_quoted():
    """shlex.quote prevents shell metacharacters in skill names from running."""
    spec, _ = Pi(_ANTHROPIC_CFG).install_skills(
        _empty_spec(),
        "Task",
        "/tmp/x",
        ["skill; echo hacked"],
        {"skill; echo hacked": "skills"},
    )
    assert "'skill; echo hacked'" in spec.setup_command
    sanitised = spec.setup_command.replace("'skill; echo hacked'", "SAFE")
    assert "echo hacked" not in sanitised
