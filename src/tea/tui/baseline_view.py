from __future__ import annotations

from tea.baseline import Regression
from tea.tui import _PASS, _bold_cyan, _c, _dim, _red, _row


class BaselineComparisonView:
    """Renders the warn-only baseline comparison section."""

    def __init__(self, regressions: list[Regression]) -> None:
        self._regressions = regressions

    def render(self) -> None:
        print(f"\n  {_bold_cyan('baseline comparison')}\n")
        if not self._regressions:
            print(_row(_PASS, _dim("metrics"), _dim("in line with baseline")))
            print()
            return

        for r in self._regressions:
            print(
                _row(
                    _c("33", "⚠"),
                    f"{r.test} · {r.metric}",
                    _red(self._delta(r)),
                )
            )
        print()

    @staticmethod
    def _delta(r: Regression) -> str:
        base = r.metric.format(r.baseline_value)
        cur = r.metric.format(r.current_value)
        pct = r.pct_change * 100
        sign = "+" if pct >= 0 else ""
        return f"{base} → {cur}  ({sign}{pct:.0f}%)"
