from __future__ import annotations

from tea._context import _active_checks
from tea.agent.agent_run import AgentRun
from tea.judge import Judge, default_judge

# Every ``check_*`` helper follows the same shape:
#   - takes the completed ``AgentRun`` as its first positional argument,
#   - accepts an optional ``description`` to override the generated label,
#   - delegates the pass/fail bookkeeping to ``check()`` and returns its result.


def check(label: str, condition: bool) -> bool:
    """Record a named assertion.

    Inside a ``TestRunner`` the result is recorded as pass/fail and the run
    keeps going; outside one it raises :class:`AssertionError` on failure.

    Args:
        label: Human-readable description of what is being asserted.
        condition: The boolean outcome of the assertion.

    Returns:
        The evaluated condition as a ``bool``.
    """
    checks = _active_checks.get(None)
    if checks is not None:
        checks.append((label, bool(condition)))
        return bool(condition)
    if not condition:
        raise AssertionError(label)
    return True


def check_skill_used(run: AgentRun, skill: str, description: str | None = None) -> bool:
    """Assert that the agent invoked a given skill during the run.

    Args:
        run: The completed agent run to inspect.
        skill: Name of the skill expected to have been used.
        description: Optional custom label; defaults to a generated one.

    Returns:
        ``True`` if the skill was used, ``False`` otherwise.
    """
    label = description or f"skill '{skill}' used"
    return check(label, skill in run.skills)


def check_skill_not_used(
    run: AgentRun, skill: str, description: str | None = None
) -> bool:
    """Assert that the agent did not invoke a given skill during the run.

    Args:
        run: The completed agent run to inspect.
        skill: Name of the skill expected to be absent.
        description: Optional custom label; defaults to a generated one.

    Returns:
        ``True`` if the skill was not used, ``False`` otherwise.
    """
    label = description or f"skill '{skill}' not used"
    return check(label, skill not in run.skills)


def check_tool_used(run: AgentRun, tool: str, description: str | None = None) -> bool:
    """Assert that the agent invoked a given tool during the run.

    Args:
        run: The completed agent run to inspect.
        tool: Name of the tool expected to have been called.
        description: Optional custom label; defaults to a generated one.

    Returns:
        ``True`` if the tool was called, ``False`` otherwise.
    """
    label = description or f"tool '{tool}' used"
    return check(label, any(t.name == tool for t in run.tools))


def check_tool_not_used(
    run: AgentRun, tool: str, description: str | None = None
) -> bool:
    """Assert that the agent did not invoke a given tool during the run.

    Args:
        run: The completed agent run to inspect.
        tool: Name of the tool expected to be absent.
        description: Optional custom label; defaults to a generated one.

    Returns:
        ``True`` if the tool was not called, ``False`` otherwise.
    """
    label = description or f"tool '{tool}' not used"
    return check(label, not any(t.name == tool for t in run.tools))


def check_file_changed(
    run: AgentRun, file: str, description: str | None = None
) -> bool:
    """Assert that the agent created or modified a given file during the run.

    Args:
        run: The completed agent run to inspect.
        file: Path of the file expected to have changed.
        description: Optional custom label; defaults to a generated one.

    Returns:
        ``True`` if the file was changed, ``False`` otherwise.
    """
    label = description or f"{file} changed"
    return check(label, file in run.files_changed)


def check_file_not_changed(
    run: AgentRun, file: str, description: str | None = None
) -> bool:
    """Assert that the agent left a given file untouched during the run.

    Args:
        run: The completed agent run to inspect.
        file: Path of the file expected to be unchanged.
        description: Optional custom label; defaults to a generated one.

    Returns:
        ``True`` if the file was not changed, ``False`` otherwise.
    """
    label = description or f"{file} not changed"
    return check(label, file not in run.files_changed)


def check_diff_added(
    run: AgentRun, file: str, code: str, description: str | None = None
) -> bool:
    """Assert that a snippet appears in the added lines of a file's diff.

    Args:
        run: The completed agent run to inspect.
        file: Path of the file whose diff is inspected.
        code: Substring expected to appear in the added lines.
        description: Optional custom label; defaults to a generated one.

    Returns:
        ``True`` if ``code`` appears in the added lines, ``False`` otherwise.
    """
    label = description or f"'{code}' added in {file}"
    change = run.files_changed.get(file)
    found = change is not None and code in change.diff.added
    return check(label, found)


def check_diff_removed(
    run: AgentRun, file: str, code: str, description: str | None = None
) -> bool:
    """Assert that a snippet appears in the removed lines of a file's diff.

    Args:
        run: The completed agent run to inspect.
        file: Path of the file whose diff is inspected.
        code: Substring expected to appear in the removed lines.
        description: Optional custom label; defaults to a generated one.

    Returns:
        ``True`` if ``code`` appears in the removed lines, ``False`` otherwise.
    """
    label = description or f"'{code}' removed from {file}"
    change = run.files_changed.get(file)
    found = change is not None and code in change.diff.removed
    return check(label, found)


def _check_judge(
    output_to_evaluate: str,
    judge_prompt: str,
    min_score: float,
    judge: object | None,
) -> float:
    """Run a judge over ``output_to_evaluate`` and record the threshold check."""
    if judge is None:
        judge = default_judge()

    if not isinstance(judge, Judge):
        raise TypeError(f"judge must be a Judge instance, got {type(judge)!r}")
    result = judge.evaluate(output_to_evaluate, judge_prompt)
    label = f"judge score {result.score:.2f} >= {min_score} | {result.rationale}"
    check(label, result.score >= min_score)
    return result.score


def check_output_score(
    run: AgentRun,
    judge_prompt: str,
    output_to_evaluate: str,
    min_score: float = 0.5,
    judge: object | None = None,
) -> float:
    """Score a specific diff with an LLM judge and assert it meets a threshold.

    Args:
        run: The completed agent run to inspect.
        judge_prompt: Scoring criteria handed to the judge.
        output_to_evaluate: The diff text to evaluate, e.g. ``run.diff("file.py")``
            or ``run.transcript``.
        min_score: Minimum score (inclusive) required to pass. Defaults to 0.5.
        judge: A :class:`Judge` instance; falls back to ``default_judge()``.

    Returns:
        The judge's score as a ``float``.

    Raises:
        TypeError: If ``judge`` is provided but is not a :class:`Judge`.
    """
    return _check_judge(output_to_evaluate, judge_prompt, min_score, judge)


def check_run_score(
    run: AgentRun,
    judge_prompt: str,
    min_score: float = 0.5,
    judge: object | None = None,
) -> float:
    """Score the whole-run diff with an LLM judge and assert it meets a threshold.

    Evaluates ``run.full_diff`` — the unified diff across every file changed.

    Args:
        run: The completed agent run to inspect.
        judge_prompt: Scoring criteria handed to the judge.
        min_score: Minimum score (inclusive) required to pass. Defaults to 0.5.
        judge: A :class:`Judge` instance; falls back to ``default_judge()``.

    Returns:
        The judge's score as a ``float``.

    Raises:
        TypeError: If ``judge`` is provided but is not a :class:`Judge`.
    """
    return _check_judge(run.full_diff, judge_prompt, min_score, judge)
