from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field, replace
from typing import Any

import pytest

from tea.agent.agent import Agent
from tea.agent.agent_run import AgentRun
from tea.agent.claude_code import ClaudeCode, ClaudeCodeHarness
from tea.agent.codex import Codex
from tea.agent.harness import Harness
from tea.agent.model_config import ModelConfig
from tea.agent.pi import Pi
from tea.agent.run_builder import _discover_skills
from tea.executor import DockerSpec, ExecutionSpec, Executor, RawResult
from tea.executor.docker import DockerExecutor

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_skill(workdir: str, name: str, content: str, *, skills_dir: str) -> None:
    skill_dir = os.path.join(workdir, skills_dir, name)
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(content)


@dataclass
class _DummySpec(ExecutionSpec):
    """ExecutionSpec subclass usable in tests (DockerSpec requires `image`)."""

    pass


@dataclass
class _RecordingExecutor(Executor):
    """Capture the spec and workdir handed to the executor; return an empty result."""

    spec: ExecutionSpec | None = None
    workdir: str | None = None
    raw: RawResult = field(default_factory=lambda: RawResult("", "", 0, 0.0))

    def run(self, spec: ExecutionSpec, workdir: str | None) -> RawResult:
        self.spec = spec
        self.workdir = workdir
        return self.raw


class _PromptCapturingAgent(Agent):
    """Minimal Agent that records what the harness passes through."""

    def __init__(self) -> None:
        self.received_prompt: str | None = None

    def build_spec(self, prompt: str, timeout: int) -> ExecutionSpec:
        self.received_prompt = prompt
        return _DummySpec(command="noop", timeout=timeout)

    def parse(self, raw: RawResult) -> AgentRun:
        return AgentRun(raw=raw.stdout, steps=[], tools=[], skills=[])

    def version(self) -> str:
        return "0.0.0"

    def install_skills(self, spec, prompt, workdir, skills_dir, skills):
        return spec, prompt


# ── _discover_skills ──────────────────────────────────────────────────────────


def test_discover_skills_finds_skills_with_skill_md():
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "alpha", "# Alpha", skills_dir="skills")
        _make_skill(workdir, "beta", "# Beta", skills_dir="skills")
        skills = _discover_skills("skills", workdir)
    assert set(skills) == {"alpha", "beta"}


def test_discover_skills_honours_user_chosen_dir_name():
    """No magic default — discovery only looks where the user pointed it."""
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "in-claude", "x", skills_dir=".claude/skills")
        _make_skill(workdir, "in-custom", "x", skills_dir="eval-fixtures/skills")
        assert _discover_skills(".claude/skills", workdir) == ["in-claude"]
        assert _discover_skills("eval-fixtures/skills", workdir) == ["in-custom"]


def test_discover_skills_ignores_dirs_without_skill_md():
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "valid", "# Valid", skills_dir="skills")
        os.makedirs(os.path.join(workdir, "skills", "empty-dir"))
        skills = _discover_skills("skills", workdir)
    assert skills == ["valid"]


def test_discover_skills_returns_empty_when_no_skills_dir_on_disk():
    with tempfile.TemporaryDirectory() as workdir:
        assert _discover_skills("skills", workdir) == []


def test_discover_skills_returns_empty_when_skills_dir_unset():
    """No user-supplied path means no skills loaded — tea has no default."""
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "alpha", "x", skills_dir=".claude/skills")
        assert _discover_skills(None, workdir) == []


def test_discover_skills_returns_empty_for_none_workdir():
    assert _discover_skills("skills", None) == []


def test_discover_skills_rejects_absolute_path():
    with tempfile.TemporaryDirectory() as workdir:
        with pytest.raises(ValueError, match="must be relative to workdir"):
            _discover_skills("/abs/path/skills", workdir)


# ── Agent.install_skills is abstract — agents must implement it ──────────────


def test_agent_install_skills_is_abstract():
    """An Agent subclass missing install_skills cannot be instantiated."""

    class _MissingInstall(Agent):
        def build_spec(self, prompt, timeout):
            return _DummySpec(command="noop", timeout=timeout)

        def parse(self, raw):
            return AgentRun(raw="", steps=[], tools=[], skills=[])

        def version(self):
            return "0.0.0"

    with pytest.raises(TypeError, match="install_skills"):
        _MissingInstall()  # type: ignore[abstract]


# ── Harness wires install_skills correctly ────────────────────────────────────


def test_harness_calls_install_skills_when_skills_and_workdir(tmp_path):
    agent = _PromptCapturingAgent()
    executor = _RecordingExecutor()
    Harness(agent, executor)._execute(
        "base prompt",
        timeout=30,
        workdir=str(tmp_path),
        skills=["s"],
        skills_dir="skills",
    )
    assert agent.received_prompt == "base prompt"


def test_harness_skips_install_skills_when_no_workdir():
    calls: list[tuple[Any, ...]] = []

    class _Counter(_PromptCapturingAgent):
        def install_skills(self, spec, prompt, workdir, skills_dir, skills):
            calls.append((spec, prompt, workdir, skills_dir, skills))
            return spec, prompt

    Harness(_Counter(), _RecordingExecutor())._execute(
        "p", timeout=30, workdir=None, skills=["a"], skills_dir="skills"
    )
    assert calls == []


def test_harness_skips_install_skills_when_no_skills():
    calls: list[tuple[Any, ...]] = []

    class _Counter(_PromptCapturingAgent):
        def install_skills(self, spec, prompt, workdir, skills_dir, skills):
            calls.append((spec, prompt, workdir, skills_dir, skills))
            return spec, prompt

    with tempfile.TemporaryDirectory() as workdir:
        Harness(_Counter(), _RecordingExecutor())._execute(
            "p", timeout=30, workdir=workdir, skills=[], skills_dir="skills"
        )
    assert calls == []


def test_harness_skips_install_skills_when_no_skills_dir():
    calls: list[tuple[Any, ...]] = []

    class _Counter(_PromptCapturingAgent):
        def install_skills(self, spec, prompt, workdir, skills_dir, skills):
            calls.append((spec, prompt, workdir, skills_dir, skills))
            return spec, prompt

    with tempfile.TemporaryDirectory() as workdir:
        Harness(_Counter(), _RecordingExecutor())._execute(
            "p", timeout=30, workdir=workdir, skills=["a"], skills_dir=None
        )
    assert calls == []


# ── Harness threads skills_dir from the constructor ──────────────────────────


def test_harness_stores_skills_dir_for_run_builder():
    agent = _PromptCapturingAgent()
    h = Harness(agent, _RecordingExecutor(), skills_dir="eval-fixtures/skills")
    assert h.skills_dir == "eval-fixtures/skills"


# ── Regression: ClaudeCode/Codex must not crash with skills + workdir ────────


def test_claude_code_harness_with_skills_runs_install_skills(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(os.path, "isfile", lambda p: False)
    executor = _RecordingExecutor()
    harness = Harness(ClaudeCode(), executor)
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "regression", "# any", skills_dir="skills")
        harness._execute(
            "hello",
            timeout=30,
            workdir=workdir,
            skills=["regression"],
            skills_dir="skills",
        )
    spec = executor.spec
    assert isinstance(spec, DockerSpec)
    assert spec.setup_command is not None
    # Skills get materialised into Claude Code's native cwd location.
    assert "/workspace/.claude/skills/regression" in spec.setup_command
    assert "/workspace/skills/regression/SKILL.md" in spec.setup_command


def test_codex_harness_with_skills_runs_install_skills(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    executor = _RecordingExecutor()
    harness = Harness(Codex(), executor)
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "skill-x", "# any", skills_dir="skills")
        harness._execute(
            "hi",
            timeout=30,
            workdir=workdir,
            skills=["skill-x"],
            skills_dir="skills",
        )

    spec = executor.spec
    assert isinstance(spec, DockerSpec)
    assert spec.setup_command is not None
    assert "/home/node/.codex/skills/skill-x" in spec.setup_command


# ── Codex.install_skills ──────────────────────────────────────────────────────


def test_codex_install_skills_adds_mkdir_and_cp(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = Codex().build_spec("do stuff", 60)
    assert base.setup_command is None  # no skill commands in base spec

    spec, prompt = Codex().install_skills(
        base, "do stuff", "/tmp/anywhere", "skills", ["add-new-operation"]
    )

    assert prompt == "do stuff"  # codex doesn't touch the prompt
    assert spec.setup_command is not None
    assert "mkdir -p /home/node/.codex/skills/add-new-operation" in spec.setup_command
    assert (
        "cp /workspace/skills/add-new-operation/SKILL.md"
        " /home/node/.codex/skills/add-new-operation/SKILL.md"
    ) in spec.setup_command


def test_codex_install_skills_uses_supplied_skills_dir(monkeypatch):
    """Codex copies from the user-chosen source path, not a hardcoded one."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = Codex().build_spec("do stuff", 60)
    spec, _ = Codex().install_skills(
        base, "do stuff", "/tmp/x", "eval-fixtures/skills", ["a"]
    )
    assert "cp /workspace/eval-fixtures/skills/a/SKILL.md" in spec.setup_command


def test_codex_install_skills_multiple_skills(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = Codex().build_spec("do stuff", 60)
    spec, _ = Codex().install_skills(base, "do stuff", "/tmp/x", "skills", ["a", "b"])
    assert "cp /workspace/skills/a/SKILL.md" in spec.setup_command
    assert "cp /workspace/skills/b/SKILL.md" in spec.setup_command


def test_codex_install_skills_preserves_existing_setup(monkeypatch):
    """If build_spec ever grows other setup, install_skills chains, not replaces."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = replace(Codex().build_spec("hi", 60), setup_command="echo prelude")
    spec, _ = Codex().install_skills(base, "hi", "/tmp/x", "skills", ["s"])

    assert spec.setup_command.startswith("echo prelude && ")
    assert "/home/node/.codex/skills/s" in spec.setup_command


# ── ClaudeCode.install_skills ────────────────────────────────────────────────


def test_claude_code_install_skills_copies_into_native_path(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(os.path, "isfile", lambda p: False)
    base = ClaudeCode().build_spec("hi", 60)
    spec, prompt = ClaudeCode().install_skills(
        base, "hi", "/tmp/anywhere", "skills", ["my-skill"]
    )
    assert prompt == "hi"
    assert spec.setup_command is not None
    assert (
        "cp /workspace/skills/my-skill/SKILL.md"
        " /workspace/.claude/skills/my-skill/SKILL.md"
    ) in spec.setup_command


def test_claude_code_install_skills_skips_copy_when_source_is_native(monkeypatch):
    """If the user already chose the native location, no shell prelude needed."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(os.path, "isfile", lambda p: False)
    base = ClaudeCode().build_spec("hi", 60)
    spec, prompt = ClaudeCode().install_skills(
        base, "hi", "/tmp/anywhere", ".claude/skills", ["my-skill"]
    )
    assert spec is base
    assert prompt == "hi"


# ── ClaudeCode public properties ─────────────────────────────────────────────


def test_claude_code_model_property():
    agent = ClaudeCode(model="claude-opus-4-7")
    assert agent.model == "claude-opus-4-7"


def test_claude_code_max_turns_property():
    agent = ClaudeCode(max_turns=5)
    assert agent.max_turns == 5


# ── ClaudeCode extra_volumes constructor param ────────────────────────────────


def test_claude_code_extra_volumes_merged_into_spec(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(os.path, "isfile", lambda p: False)
    extra = {str(tmp_path): "/container/extra"}
    spec = ClaudeCode(extra_volumes=extra).build_spec("task", 60)
    assert str(tmp_path) in spec.extra_volumes
    assert spec.extra_volumes[str(tmp_path)] == "/container/extra"


def test_claude_code_extra_volumes_defaults_empty(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(os.path, "isfile", lambda p: False)
    spec = ClaudeCode().build_spec("task", 60)
    assert spec.extra_volumes == {}


# ── ClaudeCode host mount: scoped to .credentials.json, not the whole dir ────


def test_claude_code_mounts_only_credentials_file(monkeypatch):
    """The host ~/.claude mount used to leak personal skills/agents/settings."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    creds_path = os.path.expanduser("~/.claude/.credentials.json")
    monkeypatch.setattr(os.path, "isfile", lambda p: p == creds_path)
    spec = ClaudeCode().build_spec("task", 60)
    # Only the credentials file is mounted — never the full ~/.claude dir.
    assert spec.extra_volumes == {creds_path: "/home/node/.claude/.credentials.json"}


# ── ClaudeCodeHarness uses public properties ─────────────────────────────────


def test_claude_code_harness_with_api_key_threads_model_and_turns():
    agent = ClaudeCode(model="claude-sonnet-4-6", max_turns=3)
    harness = ClaudeCodeHarness(agent, DockerExecutor()).with_api_key()
    inner = harness._agent
    assert isinstance(inner, ClaudeCode)
    assert inner.model == "claude-sonnet-4-6"
    assert inner.max_turns == 3


def test_claude_code_harness_with_api_key_threads_skills_dir():
    harness = ClaudeCodeHarness(
        ClaudeCode(), DockerExecutor(), skills_dir="eval/skills"
    ).with_api_key()
    assert harness.skills_dir == "eval/skills"


# ── shell-injection regression tests ─────────────────────────────────────────


def test_claude_model_injection_is_quoted(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    spec = ClaudeCode(model="haiku; rm -rf /").build_spec("task", 60)
    assert "--model 'haiku; rm -rf /'" in spec.command
    assert "; rm -rf /" not in spec.command.split("'haiku; rm -rf /'")[1]


def test_codex_model_injection_is_quoted(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec = Codex(model="gpt`whoami`").build_spec("task", 60)
    assert "-m 'gpt`whoami`'" in spec.command


def test_codex_skill_name_injection_is_quoted(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = Codex().build_spec("task", 60)
    spec, _ = Codex().install_skills(
        base, "task", "/tmp/x", "skills", ["skill; echo hacked"]
    )
    assert spec.setup_command is not None
    assert "'skill; echo hacked'" in spec.setup_command
    sanitised = spec.setup_command.replace("'skill; echo hacked'", "SAFE")
    assert "echo hacked" not in sanitised


# ── Pi.install_skills: prompt is the delivery channel for Pi ─────────────────


def test_pi_install_skills_modifies_prompt_not_spec(tmp_path):
    cfg = ModelConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    skill_dir = tmp_path / "skills" / "add-operation"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: How to add an operation\n---\n# body\n"
    )

    pi = Pi(cfg)
    base_spec = DockerSpec(command="noop", image="x")
    spec, prompt = pi.install_skills(
        base_spec, "Do the task", str(tmp_path), "skills", ["add-operation"]
    )
    assert spec is base_spec  # Pi delivers via prompt, not spec
    assert "Available skills:" in prompt
    assert "add-operation: How to add an operation" in prompt
    assert "skills/add-operation/SKILL.md" in prompt
    assert prompt.endswith("Do the task")
