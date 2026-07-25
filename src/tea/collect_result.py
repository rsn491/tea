from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from tea.agent.agent_run import AgentRun


def _empty_check_results() -> dict[str, list[bool]]:
    return defaultdict(list)


@dataclass
class _CollectResult:
    check_results: dict[str, list[bool]] = field(default_factory=_empty_check_results)
    all_runs: list[AgentRun] = field(default_factory=list)
    run_errors: list[Exception] = field(default_factory=list)
    iterations: int = 0
    failed_iterations: int = 0
    max_failures: int = 0

    @property
    def passed(self) -> bool:
        return self.failed_iterations <= self.max_failures
