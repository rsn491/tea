from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ConfigScope:
    env_var: str
    files: dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionRequirements:
    host_network_access: bool = False
    config_scopes: list[ConfigScope] = field(default_factory=list)


@dataclass
class ExecutionSpec:
    command: str
    env: dict[str, str] = field(default_factory=dict)
    timeout: int = 300
    setup_command: str | None = None
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
