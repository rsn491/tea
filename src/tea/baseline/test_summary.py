from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tea.baseline.metric import Metric

if TYPE_CHECKING:
    from tea.runner import _CollectResult


@dataclass
class TestSummary:
    """One test's iteration success rate plus its averaged run metrics.

    `metrics` maps a metric's JSON key to a nested object ({"avg": ...}) so
    min/max/percentiles can be added later without a schema break. It is empty
    when no runs were recorded (e.g. every iteration errored).
    """

    success_rate: float
    metrics: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: _CollectResult) -> TestSummary:
        total = result.iterations
        passed = total - result.failed_iterations
        success_rate = passed / total if total else 0.0

        metrics: dict[str, dict] = {}
        if result.all_runs:
            runs = result.all_runs
            # Averages mirror the math in tui/runner_view.py.
            metrics = {
                metric.key: {"avg": statistics.mean(metric.extract(r) for r in runs)}
                for metric in Metric.run_metrics()
            }

        return cls(success_rate=success_rate, metrics=metrics)

    def value(self, metric: Metric) -> float | None:
        """This summary's value for `metric`, or None if it was not recorded."""
        if metric is Metric.SUCCESS_RATE:
            return self.success_rate
        entry = self.metrics.get(metric.key)
        return entry.get("avg") if entry else None

    def to_dict(self) -> dict:
        return {"success_rate": self.success_rate, "metrics": self.metrics}

    @classmethod
    def from_dict(cls, data: dict) -> TestSummary:
        return cls(
            success_rate=data.get("success_rate", 0.0),
            metrics=data.get("metrics", {}),
        )
