from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import ClassVar

import docker


@dataclass
class DockerRunConfig:
    image: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    timeout: int = 300
    volumes: dict[str, str] = field(default_factory=dict)  # {host_path: container_path}
    container_workdir: str | None = None
    user: str | None = None
    extra_hosts: dict[str, str] = field(default_factory=dict)


@dataclass
class DockerRunResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_s: float = 0.0


class Docker:
    """Manages in-flight Docker containers for a batch of runs.

    **Singleton access** — ``Docker.get()`` returns the instance bound to
    the current context (set by the parallel runner via ``_active_runner``)
    or the module-level singleton for sequential use.

    **Parallel shutdown** — call ``shutdown()`` from the main thread to kill
    every running container and prevent new ones from starting.  Worker
    threads detect the shutdown after ``container.wait()`` returns and raise
    ``KeyboardInterrupt``, letting the executor drain with ``wait=True``.
    """

    _singleton: ClassVar[Docker | None] = None

    def __init__(self) -> None:
        self._shutdown = False
        self._containers: list = []
        self._lock = threading.Lock()

    # ── singleton ─────────────────────────────────────────────────────────────

    @staticmethod
    def get() -> Docker:
        """Return the module-level singleton, creating it on first call."""
        if Docker._singleton is None:
            Docker._singleton = Docker()
        return Docker._singleton

    # ── public ────────────────────────────────────────────────────────────────

    def run(self, config: DockerRunConfig) -> DockerRunResult:
        with self._lock:
            if self._shutdown:
                raise RuntimeError(
                    "Docker runner is shut down; cannot start new containers"
                )

        client = docker.from_env()
        volume_binds = {
            host: {"bind": ctr, "mode": "rw"} for host, ctr in config.volumes.items()
        }
        t0 = time.monotonic()
        container = client.containers.run(
            config.image,
            config.command,
            environment=config.env or None,
            volumes=volume_binds or None,
            working_dir=config.container_workdir,
            user=config.user,
            extra_hosts=config.extra_hosts or None,
            detach=True,
            remove=False,
        )
        with self._lock:
            self._containers.append(container)
        try:
            exit_code = container.wait(timeout=config.timeout)["StatusCode"]
            # Re-check after unblocking — shutdown() may have killed us.
            if self._shutdown:
                raise KeyboardInterrupt
            duration_s = time.monotonic() - t0
            stdout = container.logs(stdout=True, stderr=False).decode(
                "utf-8", errors="replace"
            )
            stderr = container.logs(stdout=False, stderr=True).decode(
                "utf-8", errors="replace"
            )
        finally:
            with self._lock:
                try:
                    self._containers.remove(container)
                except ValueError:
                    pass
            container.remove(force=True)

        return DockerRunResult(
            stdout=stdout, stderr=stderr, exit_code=exit_code, duration_s=duration_s
        )

    def shutdown(self) -> None:
        """Prevent new containers from starting and kill every in-flight one."""
        with self._lock:
            self._shutdown = True
            containers = list(self._containers)
        for container in containers:
            try:
                container.kill()
            except Exception:
                pass
