from __future__ import annotations

import statistics
from typing import Callable

from tea.agent.agent_run import AgentRun
from tea.tui import _fail, _pass, _row
from tea.tui.theme import bold_primary, dim, error, success, warning


def print_test_header(name: str, iterations: int) -> None:
    print(f"\n  {bold_primary(name)}  {dim(f'[{iterations} iteration(s)]')}\n")


def print_test_results(
    check_results: dict[str, list[bool]],
    all_runs: list[AgentRun],
    run_errors: list[Exception],
    iterations: int,
    failed_iterations: int = 0,
    max_failures: int = 0,
) -> None:
    for check_label, results in check_results.items():
        passes = sum(results)
        total = len(results)
        pct = 100.0 * passes / total if total else 0.0
        sym = _pass() if passes == total else _fail()
        pct_str = success(f"{pct:.0f}%") if passes == total else warning(f"{pct:.0f}%")
        print(
            _row(
                sym,
                check_label,
                f"{pct_str}  {success(str(passes))} passed"
                f"  {error(str(total - passes))} failed",
            )
        )

    if all_runs:

        def _avg_row(
            metric: str, values: list[float], fmt: Callable[[float], str]
        ) -> str:
            return _row(" ", dim(metric), dim(f"avg={fmt(statistics.mean(values))}"))

        print(
            _avg_row(
                "step_count",
                [float(r.step_count) for r in all_runs],
                lambda v: f"{v:.1f}",
            )
        )
        print(
            _avg_row(
                "token_count",
                [float(r.token_count) for r in all_runs],
                lambda v: f"{v:.0f}",
            )
        )
        print(
            _avg_row(
                "duration", [r.duration_s for r in all_runs], lambda v: f"{v:.1f}s"
            )
        )

    print(_row(" ", dim("iterations"), dim(str(iterations))))

    if max_failures:
        sym = _pass() if failed_iterations <= max_failures else _fail()
        print(
            _row(
                sym,
                "verdict",
                f"{failed_iterations} failed iteration(s)"
                f" (max_failures={max_failures})",
            )
        )

    if run_errors:
        print(
            f"\n  {_fail()} "
            + error(f"{len(run_errors)} iteration(s) raised an exception:")
        )
        seen: set[str] = set()
        for e in run_errors:
            msg = f"{type(e).__name__}: {e}"
            if msg not in seen:
                seen.add(msg)
                print(f"    {error(msg)}")
    print()
