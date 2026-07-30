from __future__ import annotations

import json

from tea.agent.codex import (
    Codex,
    CodexHarness,
    _parse,
)
from tea.agent.harness import ApiKeyHarness
from tea.executor import RawResult


def test_codex_harness_uses_api_key_factory():
    # CodexHarness adopts the shared ApiKeyHarness ABC so its auth construction
    # is explicit and mirrors the contract other code-agents follow.
    harness = CodexHarness.docker()
    assert isinstance(harness, ApiKeyHarness)


def _events(*events: dict) -> str:
    return "\n".join(json.dumps(e) for e in events)


def test_parse_empty_stdout_yields_empty_run():
    run = _parse("")
    assert run.steps == []
    assert run.tools == []
    assert run.skills == []


def test_parse_ignores_non_json_and_non_item_events():
    stdout = "\n".join(
        [
            "2026-05-27T04:58:24 ERROR something happened",
            json.dumps({"type": "thread.started", "thread_id": "abc"}),
            json.dumps({"type": "turn.started"}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10}}),
            "",
        ]
    )
    run = _parse(stdout)
    assert run.steps == []
    assert run.tools == []
    assert run.skills == []


def test_parse_agent_message_yields_text_step():
    stdout = _events(
        {
            "type": "item.completed",
            "item": {"id": "item_0", "type": "agent_message", "text": "Done."},
        }
    )
    run = _parse(stdout)
    assert len(run.steps) == 1
    assert run.steps[0].type == "text"
    assert run.steps[0].content == "Done."


def test_parse_command_execution_yields_tool_use_and_result():
    stdout = _events(
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": "ls",
                "aggregated_output": "calculator.py\n",
                "exit_code": 0,
                "status": "completed",
            },
        }
    )
    run = _parse(stdout)
    assert len(run.tools) == 1
    assert run.tools[0].name == "bash"
    assert run.tools[0].input == {"command": "ls"}
    assert run.tools[0].tool_use_id == "item_1"
    step_types = [s.type for s in run.steps]
    assert step_types == ["tool_use", "tool_result"]
    assert run.steps[1].content == "calculator.py\n"


def test_parse_detects_skill_from_command_execution():
    """Codex has no explicit skill-use event, so we detect via SKILL.md reads."""
    stdout = _events(
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": "cat /home/node/.codex/skills/add-new-operation/SKILL.md",
                "aggregated_output": "...",
            },
        }
    )
    run = _parse(stdout)
    assert run.skills == ["add-new-operation"]


def test_parse_skill_detection_deduplicates():
    stdout = _events(
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": "cat skills/foo/SKILL.md && cat skills/foo/SKILL.md",
                "aggregated_output": "",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "type": "command_execution",
                "command": "head /workspace/.codex/skills/foo/SKILL.md",
                "aggregated_output": "",
            },
        },
    )
    run = _parse(stdout)
    assert run.skills == ["foo"]


def test_parse_file_change_emits_apply_patch_tool_call():
    stdout = _events(
        {
            "type": "item.completed",
            "item": {
                "id": "item_4",
                "type": "file_change",
                "changes": [{"path": "calculator.py", "kind": "update"}],
                "status": "completed",
            },
        }
    )
    run = _parse(stdout)
    assert len(run.tools) == 1
    assert run.tools[0].name == "apply_patch"
    assert run.tools[0].input == {
        "changes": [{"path": "calculator.py", "kind": "update"}]
    }


def test_parse_mcp_tool_call_uses_tool_and_arguments_fields():
    stdout = _events(
        {
            "type": "item.completed",
            "item": {
                "id": "item_5",
                "type": "mcp_tool_call",
                "server": "docs",
                "tool": "search",
                "arguments": {"q": "exec --json"},
                "result": {"content": [{"type": "text", "text": "ok"}]},
                "status": "completed",
            },
        }
    )
    run = _parse(stdout)
    assert len(run.tools) == 1
    assert run.tools[0].name == "search"
    assert run.tools[0].input == {"q": "exec --json"}
    step_types = [s.type for s in run.steps]
    assert step_types == ["tool_use", "tool_result"]


def test_parse_web_search_item_creates_tool_call():
    stdout = _events(
        {
            "type": "item.completed",
            "item": {
                "id": "item_7",
                "type": "web_search",
                "query": "codex exec --json schema",
            },
        }
    )
    run = _parse(stdout)
    assert run.tools[0].name == "web_search"
    assert run.tools[0].input == {"query": "codex exec --json schema"}


def test_parse_threads_raw_result_metadata():
    raw = RawResult(
        stdout=_events(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "hi"},
            }
        ),
        stderr="warning",
        exit_code=2,
        duration_s=1.5,
    )
    run = Codex().parse(raw)
    assert run.exit_code == 2
    assert run.stderr == "warning"
    assert run.duration_s == 1.5
    assert run.steps[0].content == "hi"


def test_build_spec_uses_json_flag_and_default_model(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec = Codex().build_spec("task", 60)
    assert "codex exec --json" in spec.command
    assert "-m gpt-5.2-codex" in spec.command


def test_codex_exposes_model_property():
    assert Codex(model="custom-model").model == "custom-model"


# ── API-key auth via env var ─────────────────────────────────────────────────


def test_build_spec_forwards_openai_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    spec = Codex().build_spec("task", 60)
    assert spec.env["OPENAI_API_KEY"] == "sk-test"


def test_build_spec_no_setup_command_without_skills(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec = Codex().build_spec("task", 60)
    assert spec.setup_command is None
    assert spec.requirements.extra_mounts == {}


def test_with_api_key_defaults_to_default_model():
    harness = CodexHarness.docker().with_api_key()
    assert isinstance(harness._agent, Codex)
    assert harness._agent.model == "gpt-5.2-codex"


def test_with_api_key_preserves_explicit_model():
    harness = CodexHarness.docker(Codex(model="gpt-5.2-codex-spark")).with_api_key()
    assert harness._agent.model == "gpt-5.2-codex-spark"


def test_with_api_key_preserves_skills_sources():
    harness = CodexHarness.docker(skills_sources=["custom/skills"]).with_api_key()
    assert harness.skills_sources == ["custom/skills"]
