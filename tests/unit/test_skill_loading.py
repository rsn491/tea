from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field, replace
from typing import Any

import pytest

from tea.agent.agent import Agent
from tea.agent.agent_run import AgentRun
from tea.agent.claude_code import ClaudeCode, ClaudeCodeHarness, _claude_docker_profile
from tea.agent.codex import Codex
from tea.agent.harness import Harness
from tea.agent.pi import Pi, PiConfig
from tea.agent.run_builder import RunBuilder, _discover_skills, _resolve_skill_sources
from tea.executor import ExecutionSpec, Executor, RawResult
from tea.executor.docker_executor import DockerExecutor

# ── helpers ───────────────────────────────────────────────────────────────────


_PI_TEST_CFG = PiConfig(
    "anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY"
)

# Pi's skill-copy destination (follows a ConfigScope-relocated agent dir).
_PI_SKILLS_DST = '"${PI_CODING_AGENT_DIR:-/home/node/.pi/agent}"/skills'


def _make_skill(workdir: str, name: str, content: str, *, skills_dir: str) -> None:
    skill_dir = os.path.join(workdir, skills_dir, name)
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(content)


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
    """Minimal Agent that records what the run pipeline passes through."""

    def __init__(self) -> None:
        self.received_prompt: str | None = None

    def build_spec(self, prompt: str, timeout: int) -> ExecutionSpec:
        self.received_prompt = prompt
        return ExecutionSpec(command="noop", timeout=timeout)

    def parse(self, raw: RawResult) -> AgentRun:
        return AgentRun(raw=raw.stdout, steps=[], tools=[], skills=[])

    def version(self) -> str:
        return "0.0.0"

    def install_skills(self, spec, prompt, workdir, skills, source_for):
        return spec, prompt


class _RecordingAgent(_PromptCapturingAgent):
    """Also records every install_skills invocation."""

    def __init__(self) -> None:
        super().__init__()
        self.install_calls: list[dict[str, Any]] = []

    def install_skills(self, spec, prompt, workdir, skills, source_for):
        self.install_calls.append(
            {
                "prompt": prompt,
                "workdir": workdir,
                "skills": list(skills),
                "source_for": dict(source_for),
                # Probed here because the tmp workdir copy is gone after run().
                "skill_md_present": {
                    name: os.path.isfile(
                        os.path.join(workdir, source_for[name], name, "SKILL.md")
                    )
                    for name in skills
                },
            }
        )
        return spec, prompt


def _recording_harness(
    defaults: tuple[str, ...] = (),
    skills_sources: list[str] | None = None,
) -> tuple[Harness, _RecordingAgent, _RecordingExecutor]:
    agent_cls = type("_Agent", (_RecordingAgent,), {"DEFAULT_SKILL_SOURCES": defaults})
    agent = agent_cls()
    executor = _RecordingExecutor()
    return Harness(agent, executor, skills_sources=skills_sources), agent, executor


# ── _resolve_skill_sources ────────────────────────────────────────────────────


def test_resolve_sources_none_uses_defaults_present_on_disk():
    """None falls back to agent defaults, filtered to those that exist."""
    with tempfile.TemporaryDirectory() as workdir:
        os.makedirs(os.path.join(workdir, ".claude/skills"))
        # .agents/skills intentionally absent — should be silently skipped.
        assert _resolve_skill_sources(
            None, (".claude/skills", ".agents/skills"), workdir
        ) == [".claude/skills"]


def test_resolve_sources_none_returns_empty_when_no_defaults_present():
    with tempfile.TemporaryDirectory() as workdir:
        assert (
            _resolve_skill_sources(None, (".claude/skills", ".agents/skills"), workdir)
            == []
        )


def test_resolve_sources_empty_list_is_explicit_opt_out():
    with tempfile.TemporaryDirectory() as workdir:
        os.makedirs(os.path.join(workdir, ".claude/skills"))
        assert _resolve_skill_sources([], (".claude/skills",), workdir) == []


def test_resolve_sources_explicit_list_replaces_defaults():
    with tempfile.TemporaryDirectory() as workdir:
        os.makedirs(os.path.join(workdir, ".claude/skills"))
        os.makedirs(os.path.join(workdir, "custom"))
        assert _resolve_skill_sources(["custom"], (".claude/skills",), workdir) == [
            "custom"
        ]


def test_resolve_sources_explicit_missing_path_raises():
    """Explicit means explicit: a missing path is a configuration error."""
    with tempfile.TemporaryDirectory() as workdir:
        with pytest.raises(ValueError, match="does not exist"):
            _resolve_skill_sources(["nope"], (), workdir)


def test_resolve_sources_rejects_absolute_path():
    with tempfile.TemporaryDirectory() as workdir:
        with pytest.raises(ValueError, match="must be relative to workdir"):
            _resolve_skill_sources(["/abs/skills"], (), workdir)


def test_resolve_sources_returns_empty_for_none_workdir():
    assert _resolve_skill_sources(None, (".claude/skills",), None) == []
    assert _resolve_skill_sources(["custom"], (), None) == []


# ── _discover_skills ──────────────────────────────────────────────────────────


def test_discover_skills_finds_skills_with_skill_md():
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "alpha", "# Alpha", skills_dir="skills")
        _make_skill(workdir, "beta", "# Beta", skills_dir="skills")
        skills, source_for = _discover_skills(["skills"], workdir)
    assert set(skills) == {"alpha", "beta"}
    assert source_for == {"alpha": "skills", "beta": "skills"}


def test_discover_skills_honours_user_chosen_dir_name():
    """Discovery only looks where the caller pointed it."""
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "in-claude", "x", skills_dir=".claude/skills")
        _make_skill(workdir, "in-custom", "x", skills_dir="eval-fixtures/skills")
        skills, _ = _discover_skills([".claude/skills"], workdir)
        assert skills == ["in-claude"]
        skills, _ = _discover_skills(["eval-fixtures/skills"], workdir)
        assert skills == ["in-custom"]


def test_discover_skills_ignores_dirs_without_skill_md():
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "valid", "# Valid", skills_dir="skills")
        os.makedirs(os.path.join(workdir, "skills", "empty-dir"))
        skills, _ = _discover_skills(["skills"], workdir)
    assert skills == ["valid"]


def test_discover_skills_returns_empty_when_source_absent_on_disk():
    with tempfile.TemporaryDirectory() as workdir:
        skills, source_for = _discover_skills(["skills"], workdir)
    assert skills == [] and source_for == {}


def test_discover_skills_returns_empty_when_no_sources():
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "alpha", "x", skills_dir=".claude/skills")
        skills, source_for = _discover_skills([], workdir)
    assert skills == [] and source_for == {}


def test_discover_skills_returns_empty_for_none_workdir():
    skills, source_for = _discover_skills(["skills"], None)
    assert skills == [] and source_for == {}


def test_discover_skills_multi_source_merges():
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "alpha", "x", skills_dir=".claude/skills")
        _make_skill(workdir, "beta", "x", skills_dir=".agents/skills")
        skills, source_for = _discover_skills(
            [".claude/skills", ".agents/skills"], workdir
        )
    assert set(skills) == {"alpha", "beta"}
    assert source_for["alpha"] == ".claude/skills"
    assert source_for["beta"] == ".agents/skills"


def test_discover_skills_conflict_first_source_wins():
    """Same skill name in two sources: earlier wins, later is skipped."""
    with tempfile.TemporaryDirectory() as workdir:
        _make_skill(workdir, "dup", "claude version", skills_dir=".claude/skills")
        _make_skill(workdir, "dup", "shared version", skills_dir=".agents/skills")
        skills, source_for = _discover_skills(
            [".claude/skills", ".agents/skills"], workdir
        )
    assert skills == ["dup"]
    assert source_for == {"dup": ".claude/skills"}


# ── Agent.install_skills is abstract — agents must implement it ──────────────


def test_agent_install_skills_is_abstract():
    """An Agent subclass missing install_skills cannot be instantiated."""

    class _MissingInstall(Agent):
        def build_spec(self, prompt, timeout):
            return ExecutionSpec(command="noop", timeout=timeout)

        def parse(self, raw):
            return AgentRun(raw="", steps=[], tools=[], skills=[])

        def version(self):
            return "0.0.0"

    with pytest.raises(TypeError, match="install_skills"):
        _MissingInstall()  # type: ignore[abstract]


# ── The run pipeline wires install_skills correctly ───────────────────────────


def test_run_calls_install_skills_when_skills_and_workdir(tmp_path):
    harness, agent, _ = _recording_harness()
    _make_skill(str(tmp_path), "s", "# any", skills_dir="skills")
    harness.prompt("base prompt").workdir(str(tmp_path)).skills_from(["skills"]).run()

    assert len(agent.install_calls) == 1
    call = agent.install_calls[0]
    assert call["prompt"] == "base prompt"
    assert call["skills"] == ["s"]
    assert call["source_for"] == {"s": "skills"}
    # install_skills saw the tmp workdir copy, with the skill inside it.
    assert call["workdir"] != str(tmp_path)
    assert call["skill_md_present"] == {"s": True}


def test_run_skips_install_skills_when_no_workdir():
    harness, agent, _ = _recording_harness(defaults=(".claude/skills",))
    harness.prompt("p").run()
    assert agent.install_calls == []


def test_run_skips_install_skills_when_no_skills(tmp_path):
    harness, agent, _ = _recording_harness(defaults=(".claude/skills",))
    harness.prompt("p").workdir(str(tmp_path)).run()
    assert agent.install_calls == []


# ── Harness threads skills_sources from the constructor ──────────────────────


def test_harness_stores_skills_sources_for_run_builder():
    agent = _PromptCapturingAgent()
    h = Harness(agent, _RecordingExecutor(), skills_sources=["eval-fixtures/skills"])
    assert h.skills_sources == ["eval-fixtures/skills"]


def test_harness_default_skill_sources_reads_from_agent():
    """The harness exposes the agent's class-level defaults to RunBuilder."""
    h = Harness(ClaudeCode(), _RecordingExecutor())
    assert h.default_skill_sources == (".claude/skills", ".agents/skills")


# ── Default discovery per agent ──────────────────────────────────────────────


def test_claude_code_default_sources():
    assert ClaudeCode.DEFAULT_SKILL_SOURCES == (".claude/skills", ".agents/skills")


def test_codex_default_sources():
    assert Codex.DEFAULT_SKILL_SOURCES == (".codex/skills", ".agents/skills")


def test_pi_default_sources():
    assert Pi.DEFAULT_SKILL_SOURCES == (".pi/skills", ".agents/skills")


# ── Regression: ClaudeCode/Codex must not crash with skills + workdir ────────


def test_claude_code_harness_with_skills_runs_install_skills(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    executor = _RecordingExecutor()
    harness = Harness(ClaudeCode(), executor)
    _make_skill(str(tmp_path), "regression", "# any", skills_dir="skills")
    harness.prompt("hello").workdir(str(tmp_path)).skills_from(["skills"]).run()

    spec = executor.spec
    assert isinstance(spec, ExecutionSpec)
    assert spec.setup_command is not None
    # Skills get materialised into Claude Code's native cwd location.
    assert "/workspace/.claude/skills/regression" in spec.setup_command
    assert "/workspace/skills/regression/SKILL.md" in spec.setup_command


def test_codex_harness_with_skills_runs_install_skills(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    executor = _RecordingExecutor()
    harness = Harness(Codex(), executor)
    _make_skill(str(tmp_path), "skill-x", "# any", skills_dir="skills")
    harness.prompt("hi").workdir(str(tmp_path)).skills_from(["skills"]).run()

    spec = executor.spec
    assert isinstance(spec, ExecutionSpec)
    assert spec.setup_command is not None
    assert "/home/node/.codex/skills/skill-x" in spec.setup_command


# ── Codex.install_skills ──────────────────────────────────────────────────────


def test_codex_install_skills_adds_mkdir_and_cp(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = Codex().build_spec("do stuff", 60)
    assert base.setup_command is None  # no skill commands in base spec

    spec, prompt = Codex().install_skills(
        base,
        "do stuff",
        "/tmp/anywhere",
        ["add-new-operation"],
        {"add-new-operation": "skills"},
    )

    assert prompt == "do stuff"  # codex doesn't touch the prompt
    assert spec.setup_command is not None
    assert "mkdir -p /home/node/.codex/skills/add-new-operation" in spec.setup_command
    assert (
        "cp /workspace/skills/add-new-operation/SKILL.md"
        " /home/node/.codex/skills/add-new-operation/SKILL.md"
    ) in spec.setup_command


def test_codex_install_skills_uses_per_skill_source_path(monkeypatch):
    """Codex copies each skill from its own discovered source."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = Codex().build_spec("do stuff", 60)
    spec, _ = Codex().install_skills(
        base,
        "do stuff",
        "/tmp/x",
        ["a", "b"],
        {"a": ".codex/skills", "b": ".agents/skills"},
    )
    assert "cp /workspace/.codex/skills/a/SKILL.md" in spec.setup_command
    assert "cp /workspace/.agents/skills/b/SKILL.md" in spec.setup_command


def test_codex_install_skills_multiple_skills(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = Codex().build_spec("do stuff", 60)
    spec, _ = Codex().install_skills(
        base, "do stuff", "/tmp/x", ["a", "b"], {"a": "skills", "b": "skills"}
    )
    assert "cp /workspace/skills/a/SKILL.md" in spec.setup_command
    assert "cp /workspace/skills/b/SKILL.md" in spec.setup_command


def test_codex_install_skills_preserves_existing_setup(monkeypatch):
    """If build_spec ever grows other setup, install_skills chains, not replaces."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    base = replace(Codex().build_spec("hi", 60), setup_command="echo prelude")
    spec, _ = Codex().install_skills(base, "hi", "/tmp/x", ["s"], {"s": "skills"})

    assert spec.setup_command.startswith("echo prelude && ")
    assert "/home/node/.codex/skills/s" in spec.setup_command


# ── ClaudeCode.install_skills ────────────────────────────────────────────────


def test_claude_code_install_skills_copies_into_native_path(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    base = ClaudeCode().build_spec("hi", 60)
    spec, prompt = ClaudeCode().install_skills(
        base, "hi", "/tmp/anywhere", ["my-skill"], {"my-skill": "skills"}
    )
    assert prompt == "hi"
    assert spec.setup_command is not None
    assert (
        "cp /workspace/skills/my-skill/SKILL.md"
        " /workspace/.claude/skills/my-skill/SKILL.md"
    ) in spec.setup_command


def test_claude_code_install_skills_skips_copy_when_source_is_native(monkeypatch):
    """If every skill came from the native location, no shell prelude needed."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    base = ClaudeCode().build_spec("hi", 60)
    spec, prompt = ClaudeCode().install_skills(
        base, "hi", "/tmp/anywhere", ["my-skill"], {"my-skill": ".claude/skills"}
    )
    assert spec is base
    assert prompt == "hi"


def test_claude_code_install_skills_mixed_sources(monkeypatch):
    """Native-path skill skipped; non-native skill still gets a cp."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    base = ClaudeCode().build_spec("hi", 60)
    spec, _ = ClaudeCode().install_skills(
        base,
        "hi",
        "/tmp/x",
        ["native", "shared"],
        {"native": ".claude/skills", "shared": ".agents/skills"},
    )
    assert spec.setup_command is not None
    # The native skill is not copied (it already lives where Claude looks).
    assert "/workspace/.claude/skills/native/SKILL.md" not in (
        spec.setup_command.replace("/workspace/.claude/skills/shared/SKILL.md", "")
    )
    # The shared skill is translated to the native path.
    assert (
        "cp /workspace/.agents/skills/shared/SKILL.md"
        " /workspace/.claude/skills/shared/SKILL.md"
    ) in spec.setup_command


# ── ClaudeCode public properties ─────────────────────────────────────────────


def test_claude_code_model_property():
    agent = ClaudeCode(model="claude-opus-4-7")
    assert agent.model == "claude-opus-4-7"


def test_claude_code_max_turns_property():
    agent = ClaudeCode(max_turns=5)
    assert agent.max_turns == 5


# ── ClaudeCode extra_volumes constructor param ────────────────────────────────


def test_claude_code_extra_volumes_become_extra_mounts(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    extra = {str(tmp_path): "/container/extra"}
    spec = ClaudeCode(extra_volumes=extra).build_spec("task", 60)
    assert spec.requirements.extra_mounts[str(tmp_path)] == "/container/extra"


def test_claude_code_extra_volumes_defaults_empty(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    spec = ClaudeCode().build_spec("task", 60)
    assert spec.requirements.extra_mounts == {}


# ── ClaudeCodeHarness uses public properties ─────────────────────────────────


def test_claude_code_harness_with_api_key_threads_model_and_turns():
    agent = ClaudeCode(model="claude-sonnet-4-6", max_turns=3)
    harness = ClaudeCodeHarness(
        agent, DockerExecutor(_claude_docker_profile)
    ).with_api_key()
    inner = harness._agent
    assert isinstance(inner, ClaudeCode)
    assert inner.model == "claude-sonnet-4-6"
    assert inner.max_turns == 3


def test_claude_code_harness_with_api_key_threads_skills_sources():
    harness = ClaudeCodeHarness(
        ClaudeCode(),
        DockerExecutor(_claude_docker_profile),
        skills_sources=["eval/skills"],
    ).with_api_key()
    assert harness.skills_sources == ["eval/skills"]


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
        base,
        "task",
        "/tmp/x",
        ["skill; echo hacked"],
        {"skill; echo hacked": "skills"},
    )
    assert spec.setup_command is not None
    assert "'skill; echo hacked'" in spec.setup_command
    sanitised = spec.setup_command.replace("'skill; echo hacked'", "SAFE")
    assert "echo hacked" not in sanitised


# ── Pi.install_skills: copies into Pi's native discovery path ────────────────


def test_pi_install_skills_copies_into_native_path():
    """Pi auto-discovers skills from <agent-dir>/skills/<name>/SKILL.md.

    See https://pi.dev/docs/latest/skills — directories containing SKILL.md
    under the agent dir's skills/ are scanned recursively at startup.
    """
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    base_spec = ExecutionSpec(command="noop")
    spec, prompt = Pi(cfg).install_skills(
        base_spec,
        "Do the task",
        "/tmp/anywhere",
        ["add-operation"],
        {"add-operation": "skills"},
    )
    assert prompt == "Do the task"  # Pi doesn't touch the prompt
    assert spec.setup_command is not None
    assert f"cp -R /workspace/skills/add-operation {_PI_SKILLS_DST}/" in (
        spec.setup_command
    )


# ── End-to-end RunBuilder behaviour ──────────────────────────────────────────


def test_run_builder_uses_agent_defaults_when_sources_unset(tmp_path):
    """No explicit sources → search the agent's conventional paths."""
    _make_skill(str(tmp_path), "hello", "x", skills_dir=".claude/skills")
    harness, agent, _ = _recording_harness(
        defaults=(".claude/skills", ".agents/skills")
    )
    RunBuilder.prompt(harness, "do thing").workdir(str(tmp_path)).run()

    assert agent.install_calls[0]["skills"] == ["hello"]
    assert agent.install_calls[0]["source_for"] == {"hello": ".claude/skills"}


def test_run_builder_explicit_sources_replaces_defaults(tmp_path):
    # Default location has a skill that should be IGNORED because the harness
    # was configured with an explicit source list.
    _make_skill(str(tmp_path), "default-only", "x", skills_dir=".claude/skills")
    _make_skill(str(tmp_path), "chosen", "x", skills_dir="custom")

    harness, agent, _ = _recording_harness(
        defaults=(".claude/skills", ".agents/skills"), skills_sources=["custom"]
    )
    RunBuilder.prompt(harness, "do thing").workdir(str(tmp_path)).run()

    assert agent.install_calls[0]["skills"] == ["chosen"]
    assert agent.install_calls[0]["source_for"] == {"chosen": "custom"}


def test_run_builder_skills_from_empty_list_disables_loading(tmp_path):
    _make_skill(str(tmp_path), "hello", "x", skills_dir=".claude/skills")
    harness, agent, _ = _recording_harness(defaults=(".claude/skills",))
    RunBuilder.prompt(harness, "do thing").workdir(str(tmp_path)).skills_from(
        []
    ).run()

    assert agent.install_calls == []


def test_run_builder_skills_from_string_normalises_to_list(tmp_path):
    """Passing a single path string is a convenience for ``[path]``."""
    _make_skill(str(tmp_path), "alpha", "x", skills_dir="custom")
    harness, agent, _ = _recording_harness()
    RunBuilder.prompt(harness, "do thing").workdir(str(tmp_path)).skills_from(
        "custom"
    ).run()

    assert agent.install_calls[0]["skills"] == ["alpha"]
    assert agent.install_calls[0]["source_for"] == {"alpha": "custom"}


def test_run_builder_symlinked_skill_lands_as_real_file(tmp_path):
    """A symlinked skill bundle must be dereferenced into the tmp workdir copy
    so it survives the bind mount into the container."""

    # Real skill content lives outside the workdir.
    external = tmp_path / "external" / "extskill"
    external.mkdir(parents=True)
    (external / "SKILL.md").write_text("# external\n")

    workdir = tmp_path / "workdir"
    (workdir / ".claude" / "skills").mkdir(parents=True)
    os.symlink(str(external), str(workdir / ".claude" / "skills" / "extskill"))

    seen: dict[str, Any] = {}

    class _SymlinkProbe(_PromptCapturingAgent):
        DEFAULT_SKILL_SOURCES = (".claude/skills",)

        def install_skills(self, spec, prompt, wd, skills, source_for):
            # The tmp copy is deleted after run(); probe while it exists.
            link = os.path.join(wd, ".claude/skills/extskill")
            seen["skills"] = list(skills)
            seen["skill_md_is_real"] = os.path.isfile(
                os.path.join(link, "SKILL.md")
            ) and not os.path.islink(link)
            return spec, prompt

    harness = Harness(_SymlinkProbe(), _RecordingExecutor())
    RunBuilder.prompt(harness, "do thing").workdir(str(workdir)).run()

    assert seen["skills"] == ["extskill"]
    assert seen["skill_md_is_real"] is True


def test_run_builder_workdir_copy_is_world_accessible(tmp_path):
    """The tmp workdir copy must be usable by the container user even when it
    differs from the host user (mkdtemp alone yields an untraversable 0o700)."""
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "file.txt").write_text("x")

    seen: dict[str, int] = {}

    @dataclass
    class _StatExecutor(Executor):
        def run(self, spec: ExecutionSpec, workdir: str | None) -> RawResult:
            seen["root"] = os.stat(workdir).st_mode & 0o777
            seen["dir"] = os.stat(os.path.join(workdir, "sub")).st_mode & 0o777
            seen["file"] = (
                os.stat(os.path.join(workdir, "sub", "file.txt")).st_mode & 0o777
            )
            return RawResult("", "", 0, 0.0)

    Harness(_PromptCapturingAgent(), _StatExecutor()).prompt("p").workdir(
        str(tmp_path)
    ).run()

    assert seen["root"] == 0o777
    assert seen["dir"] & 0o007 == 0o007  # world rwx on dirs
    assert seen["file"] & 0o006 == 0o006  # world rw on files


def test_pi_harness_with_skills_runs_install_skills(tmp_path):
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    executor = _RecordingExecutor()
    harness = Harness(Pi(cfg), executor)
    _make_skill(str(tmp_path), "regression", "# any", skills_dir="skills")
    harness.prompt("hi").workdir(str(tmp_path)).skills_from(["skills"]).run()

    spec = executor.spec
    assert isinstance(spec, ExecutionSpec)
    assert spec.setup_command is not None
    assert f"cp -R /workspace/skills/regression {_PI_SKILLS_DST}/" in (
        spec.setup_command
    )


def test_pi_skill_name_injection_is_quoted():
    cfg = PiConfig("anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY")
    base = ExecutionSpec(command="noop")
    spec, _ = Pi(cfg).install_skills(
        base, "task", "/tmp/x", ["skill; echo hacked"], {"skill; echo hacked": "skills"}
    )
    assert spec.setup_command is not None
    assert "'skill; echo hacked'" in spec.setup_command
    sanitised = spec.setup_command.replace("'skill; echo hacked'", "SAFE")
    assert "echo hacked" not in sanitised


# ── path-traversal hardening on both Codex and Pi _skill_setup helpers ────────


@pytest.mark.parametrize("agent_factory", [Codex, lambda: Pi(_PI_TEST_CFG)])
@pytest.mark.parametrize("bad_name", ["../evil", "a/b", "..", ".", "a\\b"])
def test_install_skills_rejects_path_traversal(agent_factory, bad_name, monkeypatch):
    """A skill name containing path separators must be rejected by both agents.

    shlex.quote protects the shell word but not the path semantics — a name
    like "../evil" would still escape the destination directory once the
    shell strips the quotes.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    agent = agent_factory()
    base = ExecutionSpec(command="noop")
    with pytest.raises(ValueError, match="Invalid skill name"):
        agent.install_skills(base, "task", "/tmp/x", [bad_name], {bad_name: "skills"})
