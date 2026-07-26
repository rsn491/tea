from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from tea.agent.agent_run import AgentRun


def _as_int(value: float) -> str:
    return f"{value:.0f}"


def _as_float(value: float) -> str:
    return f"{value:.1f}"


def _as_seconds(value: float) -> str:
    return f"{value:.1f}s"


def _as_percent(value: float) -> str:
    return f"{value:.0%}"


class Metric(Enum):
    """A measured quantity: its JSON key, display format, and regression rule.

    `extract` pulls the value from an AgentRun for per-run metrics; it is None
    for metrics derived elsewhere (e.g. success_rate, computed from iteration
    counts). `higher_is_better` selects the regression rule: metrics where lower
    is better regress on a relative rise beyond the tolerance, while metrics
    where higher is better regress on an absolute drop beyond it.
    """

    TOKEN_COUNT = ("token_count", _as_int, False, lambda run: float(run.token_count))
    STEP_COUNT = ("step_count", _as_float, False, lambda run: float(run.step_count))
    DURATION = ("duration", _as_seconds, False, lambda run: run.duration_s)
    SUCCESS_RATE = ("success_rate", _as_percent, True, None)

    def __init__(
        self,
        key: str,
        fmt: Callable[[float], str],
        higher_is_better: bool,
        extract: Callable[[AgentRun], float] | None,
    ) -> None:
        self.key = key
        self._fmt = fmt
        self.higher_is_better = higher_is_better
        self._extract = extract

    def __str__(self) -> str:
        return self.key

    @classmethod
    def run_metrics(cls) -> list[Metric]:
        """Metrics measured per AgentRun (everything with an extractor)."""
        return [m for m in cls if m._extract is not None]

    def extract(self, run: AgentRun) -> float:
        assert self._extract is not None, f"{self} is not a per-run metric"
        return self._extract(run)

    def format(self, value: float) -> str:
        return self._fmt(value)

    def regressed(self, baseline: float, current: float, tol: float) -> bool:
        if self.higher_is_better:
            return baseline - current > tol  # absolute drop
        if baseline == 0:
            return False
        return (current - baseline) / baseline > tol  # relative rise

    def pct_change(self, baseline: float, current: float) -> float:
        if baseline == 0:
            return 0.0
        return (current - baseline) / baseline
