from __future__ import annotations

from dataclasses import dataclass

from tea.baseline.metric import Metric


@dataclass
class Regression:
    """A single metric that worsened against a stored baseline."""

    test: str
    metric: Metric
    baseline_value: float
    current_value: float
    pct_change: float
