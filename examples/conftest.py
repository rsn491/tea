from __future__ import annotations

from harntest.agent import RunBuilder
from harntest.models import AgentRun

_runs: list[AgentRun] = []

_original_run = RunBuilder.run


def _capturing_run(self: RunBuilder) -> AgentRun:
    result = _original_run(self)
    _runs.append(result)
    return result


RunBuilder.run = _capturing_run  # type: ignore[method-assign]

_COL = 22


def _line(name: str, value: str) -> str:
    return f"  {name}{'.' * (_COL - len(name))}: {value}"


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not _runs:
        return
    terminalreporter.write_sep("=", "harntest agent runs")
    run = _runs[-1]
    terminalreporter.write_line(_line("steps", str(run.step_count)))
    terminalreporter.write_line(_line("tokens", str(run.token_count)))
    terminalreporter.write_line(_line("duration", f"{run.duration_s:.1f}s"))
