from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ConfigScope:
    """A fresh, isolated config directory the executor materialises per run.

    The agent declares the files it needs and the env var its CLI reads to
    locate them; the executor writes the files somewhere reachable from the
    execution environment, points ``env_var`` at that directory, and cleans
    up after the run.
    """

    env_var: str
    files: dict[str, str] = field(default_factory=dict)  # {relative_path: content}


@dataclass
class ExecutionRequirements:
    """Executor-agnostic needs an agent declares for a run.

    Each executor translates these into its own mechanism (e.g. DockerExecutor
    maps ``host_network_access`` to a ``host.docker.internal`` extra host and
    materialises ``config_scopes`` as bind-mounted tmp dirs).
    """

    host_network_access: bool = False
    config_scopes: list[ConfigScope] = field(default_factory=list)
    # {host_path: container_path} opt-in host mounts. Prefer config_scopes for
    # config files — host mounts leak host state into the run.
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
