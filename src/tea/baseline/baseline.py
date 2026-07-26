from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tea.baseline.metric import Metric
from tea.baseline.regression import Regression
from tea.baseline.test_summary import TestSummary

# Bump only on incompatible changes to the on-disk shape.
SCHEMA_VERSION = 1

# Fraction a metric may drift before it counts as a regression.
DEFAULT_TOLERANCE = 0.10


@dataclass
class Baseline:
    """A versioned, per-test record of metrics, storable as JSON."""

    tests: dict[str, TestSummary] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "tests": {name: s.to_dict() for name, s in self.tests.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> Baseline:
        version = data.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported baseline schema_version {version}")
        tests = {
            name: TestSummary.from_dict(s) for name, s in data.get("tests", {}).items()
        }
        return cls(tests=tests, schema_version=version)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> Baseline:
        with path.open() as f:
            return cls.from_dict(json.load(f))

    def compare(
        self, previous: Baseline, tol: float = DEFAULT_TOLERANCE
    ) -> list[Regression]:
        """Report metrics in `self` that regressed against `previous`.

        A higher-is-worse metric regresses when it rises by more than `tol`
        (relative); success_rate regresses when it drops by more than `tol`
        (absolute). Tests or metrics absent from `previous` are skipped.
        """
        regressions: list[Regression] = []
        for name, prev in previous.tests.items():
            cur = self.tests.get(name)
            if cur is None:
                continue

            for metric in Metric:
                base = prev.value(metric)
                current = cur.value(metric)
                if base is None or current is None:
                    continue
                if metric.regressed(base, current, tol):
                    regressions.append(
                        Regression(
                            name,
                            metric,
                            base,
                            current,
                            metric.pct_change(base, current),
                        )
                    )

        return regressions
