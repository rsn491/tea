from __future__ import annotations

from harntest._context import _active_checks
from harntest.agent.agent_run import AgentRun


def check(label: str, condition: bool) -> bool:
    """Named assertion.

    Inside TestRunner it records pass/fail; outside it raises on failure.
    """
    checks = _active_checks.get(None)
    if checks is not None:
        checks.append((label, bool(condition)))
        return bool(condition)
    if not condition:
        raise AssertionError(label)
    return True


def check_skill_used(run: AgentRun, skill: str, description: str | None = None) -> bool:
    label = description or f"skill '{skill}' used"
    return check(label, skill in run.skills)


def check_diff_added(
    run: AgentRun, file: str, code: str, description: str | None = None
) -> bool:
    label = description or f"'{code}' added in {file}"
    change = run.files_changed.get(file)
    found = change is not None and code in change.diff.added
    return check(label, found)


def check_judge_task(
    run: AgentRun,
    *,
    diff: str,
    prompt: str,
    min_score: float = 0.5,
    judge: object | None = None,
) -> float:
    from harntest.judge import Judge, default_judge

    if judge is None:
        judge = default_judge()

    assert isinstance(judge, Judge)
    result = judge.evaluate(diff, prompt)
    label = f"judge score {result.score:.2f} >= {min_score} | {result.rationale}"
    check(label, result.score >= min_score)
    return result.score
