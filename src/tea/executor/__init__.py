"""Executor-agnostic execution types.

Deliberately free of any concrete executor: importing this package must not
pull in the Docker SDK. ``DockerExecutor`` and ``DockerProfile`` live in — and
are imported from — ``tea.executor.docker_executor``.
"""

from .executor import (
    ExecutionRequirements,
    ExecutionSpec,
    Executor,
    RawResult,
)

__all__ = [
    "Executor",
    "ExecutionSpec",
    "ExecutionRequirements",
    "RawResult",
]
