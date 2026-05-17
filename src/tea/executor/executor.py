from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExecutionRequirements:
    """What an agent needs from the executor — executor-agnostic declarations.

    DockerExecutor translates these into Docker primitives:
      host_network_access → extra_hosts["host.docker.internal"] = "host-gateway"
      extra_mounts        → extra_volumes {host_path: container_path}
    """

    host_network_access: bool = False
    extra_mounts: dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionSpec:
    """Environment-agnostic execution spec. Extend for executor-specific fields."""

    command: str
    env: dict[str, str] = field(default_factory=dict)
    timeout: int = 300
    requirements: ExecutionRequirements = field(default_factory=ExecutionRequirements)


@dataclass
class DockerSpec(ExecutionSpec):
    """ExecutionSpec extended with Docker-specific fields."""

    image: str = ""
    setup_command: str | None = None
    user: str | None = None

    def __post_init__(self) -> None:
        if not self.image:
            raise ValueError("DockerSpec.image must be set")


@dataclass
class RawResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_s: float = 0.0


class Executor(ABC):
    @abstractmethod
    def run(self, spec: ExecutionSpec, workdir: str | None) -> RawResult: ...
