from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExecutionRequirements:
    """Executor-agnostic needs an agent declares for a run.

    Each executor translates these into its own mechanism — e.g.
    ``DockerExecutor`` maps ``host_network_access`` to a
    ``host.docker.internal`` extra host and ``extra_mounts`` to bind mounts.
    """

    host_network_access: bool = False
    # {host_path: container_path} opt-in host mounts.
    extra_mounts: dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionSpec:
    """Environment-agnostic description of a single agent run."""

    command: str
    env: dict[str, str] = field(default_factory=dict)
    timeout: int = 300
    setup_command: str | None = None  # per-run dynamic setup (e.g. skill installs)
    requirements: ExecutionRequirements = field(default_factory=ExecutionRequirements)


@dataclass
class RawResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_s: float = 0.0


class Executor(ABC):
    @abstractmethod
    def run(self, spec: ExecutionSpec, workdir: str | None) -> RawResult: ...
