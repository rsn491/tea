from __future__ import annotations

import os
import tempfile

from tea.agent.agent import Agent
from tea.agent.agent_run import AgentRun
from tea.agent.claude_code import ClaudeCode
from tea.agent.codex import Codex
from tea.agent.run_builder import _discover_skills
from tea.executor import ExecutionSpec, RawResult

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_skill(workdir: str, name: str, content: str) -> None:
    skill_dir = os.path.join(workdir, ".claude", "skills", name)
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(content)


# ── _discover_skills ──────────────────────────────────────────────────────────


def test_discover_skills_finds_skills_with_skill_md():
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "alpha", "# Alpha")
        _make_skill(workdir, "beta", "# Beta")
        skills = _discover_skills(workdir)
    assert set(skills) == {"alpha", "beta"}


def test_discover_skills_ignores_dirs_without_skill_md():
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "valid", "# Valid")
        os.makedirs(os.path.join(workdir, ".claude", "skills", "empty-dir"))
        skills = _discover_skills(workdir)
    assert skills == ["valid"]


def test_discover_skills_returns_empty_when_no_skills_dir():
    with tempfile.TemporaryDirectory() as workdir:
        assert _discover_skills(workdir) == []


def test_discover_skills_returns_empty_for_none():
    assert _discover_skills(None) == []


# ── Codex.build_spec with skills ──────────────────────────────────────────────


def test_codex_build_spec_with_skills_has_mkdir_and_cp(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec = Codex().build_spec("do stuff", 60, ["add-new-operation"])

    assert "mkdir -p /home/node/.codex/skills/add-new-operation" in spec.setup_command
    assert (
        "cp /workspace/.claude/skills/add-new-operation/SKILL.md"
        " /home/node/.codex/skills/add-new-operation/SKILL.md"
    ) in spec.setup_command


def test_codex_build_spec_with_multiple_skills_has_cp_for_each(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec = Codex().build_spec("do stuff", 60, ["skill-a", "skill-b"])

    assert "cp /workspace/.claude/skills/skill-a/SKILL.md" in spec.setup_command
    assert "cp /workspace/.claude/skills/skill-b/SKILL.md" in spec.setup_command


def test_codex_build_spec_without_skills_has_no_setup(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec = Codex().build_spec("do stuff", 60)

    assert spec.setup_command is None


# ── ClaudeCode.build_spec with skills ─────────────────────────────────────────


def test_claude_code_build_spec_ignores_skills(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    spec_no_skills = ClaudeCode().build_spec("hello", 60)
    spec_with_skills = ClaudeCode().build_spec("hello", 60, ["some-skill"])

    assert spec_with_skills.command == spec_no_skills.command
    assert spec_with_skills.setup_command == spec_no_skills.setup_command


# ── Agent.prepare_skills default ──────────────────────────────────────────────


class _MinimalAgent(Agent):
    def build_spec(
        self, prompt: str, timeout: int, skills: list[str] = ()
    ) -> ExecutionSpec:  # type: ignore[override]
        raise NotImplementedError

    def parse(self, raw: RawResult) -> AgentRun:
        raise NotImplementedError


def test_agent_default_prepare_skills_is_noop():
    agent = _MinimalAgent()
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "my-skill", "# Should be ignored")
        result = agent.prepare_skills("original prompt", workdir, ["my-skill"])
    assert result == "original prompt"


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
    spec = Codex().build_spec("task", 60, ["skill; echo hacked"])
    assert "'skill; echo hacked'" in spec.setup_command
    # the injection payload must not appear outside the quoted token
    sanitised = spec.setup_command.replace("'skill; echo hacked'", "SAFE")
    assert "echo hacked" not in sanitised
