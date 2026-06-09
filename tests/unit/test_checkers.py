from __future__ import annotations

import pytest

from tea._context import _active_checks
from tea.agent.agent_run import AgentRun, FileChange, FileDiff, ToolCall
from tea.checkers import (
    check,
    check_diff_added,
    check_diff_removed,
    check_file_changed,
    check_skill_used,
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


# ── check_skill_used ──────────────────────────────────────────────────────────


def test_check_skill_used_pass():
    run = _run(skills=["add-new-operation"])
    checks = _collected(lambda: check_skill_used(run, "add-new-operation"))
    assert checks == [("skill 'add-new-operation' used", True)]


def test_check_skill_used_fail():
    run = _run(skills=[])
    checks = _collected(lambda: check_skill_used(run, "missing"))
    assert checks == [("skill 'missing' used", False)]


def test_check_skill_used_custom_description():
    run = _run(skills=["s"])
    checks = _collected(lambda: check_skill_used(run, "s", "used the skill"))
    assert checks == [("used the skill", True)]


# ── check_tool_used ───────────────────────────────────────────────────────────


def test_check_tool_used_pass():
    run = _run(tools=[ToolCall(name="Edit", input={}, tool_use_id="1")])
    checks = _collected(lambda: check_tool_used(run, "Edit"))
    assert checks == [("tool 'Edit' used", True)]


def test_check_tool_used_fail():
    run = _run(tools=[ToolCall(name="Read", input={}, tool_use_id="1")])
    checks = _collected(lambda: check_tool_used(run, "Edit"))
    assert checks == [("tool 'Edit' used", False)]


# ── check_file_changed ────────────────────────────────────────────────────────


def test_check_file_changed_pass():
    run = _run(files={"calculator.py": _change("calculator.py")})
    checks = _collected(lambda: check_file_changed(run, "calculator.py"))
    assert checks == [("calculator.py changed", True)]


def test_check_file_changed_fail():
    run = _run(files={})
    checks = _collected(lambda: check_file_changed(run, "calculator.py"))
    assert checks == [("calculator.py changed", False)]


# ── check_diff_added ──────────────────────────────────────────────────────────


def test_check_diff_added_pass():
    run = _run(files={"f.py": _change("f.py", added="def minus(): ...")})
    checks = _collected(lambda: check_diff_added(run, "f.py", "minus"))
    assert checks == [("'minus' added in f.py", True)]


def test_check_diff_added_fail_when_missing_from_added():
    run = _run(files={"f.py": _change("f.py", removed="minus")})
    checks = _collected(lambda: check_diff_added(run, "f.py", "minus"))
    assert checks == [("'minus' added in f.py", False)]


def test_check_diff_added_fail_when_file_absent():
    run = _run(files={})
    checks = _collected(lambda: check_diff_added(run, "f.py", "minus"))
    assert checks == [("'minus' added in f.py", False)]


# ── check_diff_removed ────────────────────────────────────────────────────────


def test_check_diff_removed_pass():
    run = _run(files={"f.py": _change("f.py", removed="def legacy(): ...")})
    checks = _collected(lambda: check_diff_removed(run, "f.py", "legacy"))
    assert checks == [("'legacy' removed from f.py", True)]


def test_check_diff_removed_fail_when_missing_from_removed():
    run = _run(files={"f.py": _change("f.py", added="legacy")})
    checks = _collected(lambda: check_diff_removed(run, "f.py", "legacy"))
    assert checks == [("'legacy' removed from f.py", False)]


def test_check_diff_removed_fail_when_file_absent():
    run = _run(files={})
    checks = _collected(lambda: check_diff_removed(run, "f.py", "legacy"))
    assert checks == [("'legacy' removed from f.py", False)]
