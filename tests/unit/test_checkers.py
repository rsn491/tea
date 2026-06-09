from __future__ import annotations

import pytest

from tea._context import _active_checks
from tea.agent.agent_run import AgentRun, FileChange, FileDiff, ToolCall
from tea.checkers import (
    check,
    check_diff_added,
    check_diff_removed,
    check_file_changed,
    check_file_not_changed,
    check_skill_not_used,
    check_skill_used,
    check_tool_not_used,
    check_tool_used,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _run(*, skills=None, tools=None, files=None) -> AgentRun:
    run = AgentRun(
        raw="",
        steps=[],
        tools=list(tools or []),
        skills=list(skills or []),
    )
    run._files_changed_fn = lambda: dict(files or {})
    return run


def _change(path: str, added: str = "", removed: str = "") -> FileChange:
    return FileChange(path=path, diff=FileDiff(added=added, removed=removed))


def _collected(fn):
    """Run ``fn`` inside an active-checks context and return the recorded list."""
    token = _active_checks.set([])
    try:
        fn()
        return list(_active_checks.get())
    finally:
        _active_checks.reset(token)


# ── check ─────────────────────────────────────────────────────────────────────


def test_check_records_pass_inside_runner():
    assert _collected(lambda: check("label", True)) == [("label", True)]


def test_check_records_fail_without_raising_inside_runner():
    assert _collected(lambda: check("label", False)) == [("label", False)]


def test_check_returns_condition_inside_runner():
    token = _active_checks.set([])
    try:
        assert check("label", True) is True
        assert check("label", False) is False
    finally:
        _active_checks.reset(token)


def test_check_raises_outside_runner():
    with pytest.raises(AssertionError, match="boom"):
        check("boom", False)


def test_check_returns_true_outside_runner_on_pass():
    assert check("ok", True) is True


# Outcome tests below run outside a runner (no active-checks context), so a
# passing checker returns True and a failing checker raises AssertionError.
# Label content is covered by the custom-description and check() recording tests.


# ── check_skill_used ──────────────────────────────────────────────────────────


def test_check_skill_used_pass():
    run = _run(skills=["add-new-operation"])
    assert check_skill_used(run, "add-new-operation") is True


def test_check_skill_used_fail():
    run = _run(skills=[])
    with pytest.raises(AssertionError):
        check_skill_used(run, "missing")


def test_check_skill_used_custom_description():
    run = _run(skills=["s"])
    checks = _collected(lambda: check_skill_used(run, "s", "used the skill"))
    assert checks == [("used the skill", True)]


# ── check_skill_not_used ──────────────────────────────────────────────────────


def test_check_skill_not_used_pass():
    run = _run(skills=[])
    assert check_skill_not_used(run, "forbidden") is True


def test_check_skill_not_used_fail():
    run = _run(skills=["forbidden"])
    with pytest.raises(AssertionError):
        check_skill_not_used(run, "forbidden")


# ── check_tool_used ───────────────────────────────────────────────────────────


def test_check_tool_used_pass():
    run = _run(tools=[ToolCall(name="Edit", input={}, tool_use_id="1")])
    assert check_tool_used(run, "Edit") is True


def test_check_tool_used_fail():
    run = _run(tools=[ToolCall(name="Read", input={}, tool_use_id="1")])
    with pytest.raises(AssertionError):
        check_tool_used(run, "Edit")


# ── check_tool_not_used ───────────────────────────────────────────────────────


def test_check_tool_not_used_pass():
    run = _run(tools=[ToolCall(name="Read", input={}, tool_use_id="1")])
    assert check_tool_not_used(run, "Bash") is True


def test_check_tool_not_used_fail():
    run = _run(tools=[ToolCall(name="Bash", input={}, tool_use_id="1")])
    with pytest.raises(AssertionError):
        check_tool_not_used(run, "Bash")


# ── check_file_changed ────────────────────────────────────────────────────────


def test_check_file_changed_pass():
    run = _run(files={"calculator.py": _change("calculator.py")})
    assert check_file_changed(run, "calculator.py") is True


def test_check_file_changed_fail():
    run = _run(files={})
    with pytest.raises(AssertionError):
        check_file_changed(run, "calculator.py")


# ── check_file_not_changed ────────────────────────────────────────────────────


def test_check_file_not_changed_pass():
    run = _run(files={})
    assert check_file_not_changed(run, "calculator.py") is True


def test_check_file_not_changed_fail():
    run = _run(files={"calculator.py": _change("calculator.py")})
    with pytest.raises(AssertionError):
        check_file_not_changed(run, "calculator.py")


# ── check_diff_added ──────────────────────────────────────────────────────────


def test_check_diff_added_pass():
    run = _run(files={"f.py": _change("f.py", added="def minus(): ...")})
    assert check_diff_added(run, "f.py", "minus") is True


def test_check_diff_added_fail_when_missing_from_added():
    run = _run(files={"f.py": _change("f.py", removed="minus")})
    with pytest.raises(AssertionError):
        check_diff_added(run, "f.py", "minus")


def test_check_diff_added_fail_when_file_absent():
    run = _run(files={})
    with pytest.raises(AssertionError):
        check_diff_added(run, "f.py", "minus")


# ── check_diff_removed ────────────────────────────────────────────────────────


def test_check_diff_removed_pass():
    run = _run(files={"f.py": _change("f.py", removed="def legacy(): ...")})
    assert check_diff_removed(run, "f.py", "legacy") is True


def test_check_diff_removed_fail_when_missing_from_removed():
    run = _run(files={"f.py": _change("f.py", added="legacy")})
    with pytest.raises(AssertionError):
        check_diff_removed(run, "f.py", "legacy")


def test_check_diff_removed_fail_when_file_absent():
    run = _run(files={})
    with pytest.raises(AssertionError):
        check_diff_removed(run, "f.py", "legacy")
