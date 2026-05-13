from __future__ import annotations

import statistics
from typing import Callable

from harntest.agent.agent_run import AgentRun
from harntest.tui import _FAIL, _PASS, _bold_cyan, _c, _dim, _green, _red, _row


def print_test_header(name: str, iterations: int) -> None:
    print(f"\n  {_bold_cyan(name)}  {_dim(f'[{iterations} iteration(s)]')}\n")


def print_test_results(
    check_results: dict[str, list[bool]],
    all_runs: list[AgentRun],
    run_errors: list[Exception],
    iterations: int,
) -> None:
    for check_label, results in check_results.items():
        passes = sum(results)
        total = len(results)
        pct = 100.0 * passes / total if total else 0.0
        sym = _PASS if passes == total else _FAIL
        pct_str = _green(f"{pct:.0f}%") if passes == total else _c("33", f"{pct:.0f}%")
        print(
            _row(
                sym,
                check_label,
                f"{pct_str}  {_green(str(passes))} passed  {_red(str(total - passes))} failed",
            )
        )

    if all_runs:

        def _avg_row(
            metric: str, values: list[float], fmt: Callable[[float], str]
        ) -> str:
            return _row(" ", _dim(metric), _dim(f"avg={fmt(statistics.mean(values))}"))

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

    print(_row(" ", _dim("iterations"), _dim(str(iterations))))

    if run_errors:
        print(
            f"\n  {_FAIL} {_red(f'{len(run_errors)} iteration(s) raised an exception:')}"
        )
        seen: set[str] = set()
        for e in run_errors:
            msg = f"{type(e).__name__}: {e}"
            if msg not in seen:
                seen.add(msg)
                print(f"    {_red(msg)}")
    print()
