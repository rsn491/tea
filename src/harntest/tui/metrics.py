"""Compact run metrics rendering for non-test mode."""

from __future__ import annotations

from harntest.agent.agent_run import AgentRun

_COL = 30


def _metric_line(name: str, value: str) -> str:
    """Format one metric row."""
    dots = "." * (_COL - len(name))
    return f"  {name}{dots}: {value}"


def print_metrics(run: AgentRun) -> None:
    """Print execution metrics for one run."""
    duration_str = f"{run.duration_s:.1f}s"
    lines = [
        "",
        _metric_line("step_count", str(run.step_count)),
        _metric_line("token_count", str(run.token_count)),
        _metric_line("duration", duration_str),
        _metric_line("exit_code", str(run.exit_code)),
        "",
    ]
    print("\n".join(lines))
    if run.stderr:
        print("[stderr]", run.stderr)
