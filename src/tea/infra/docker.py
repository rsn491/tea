from __future__ import annotations

import io
import json
import subprocess
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
    _singleton: ClassVar[Docker | None] = None

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url
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

    @staticmethod
    def use_colima() -> None:
        """Point the singleton at Colima's Docker socket instead of the default."""
        Docker._singleton = Docker(base_url=colima_socket())

    # ── public ────────────────────────────────────────────────────────────────

    def create_image(self, tag: str, dockerfile: str) -> None:
        client = self._client()
        try:
            client.images.get(tag)
            return
        except docker.errors.ImageNotFound:
            pass
        client.images.build(fileobj=io.BytesIO(dockerfile.encode()), tag=tag, rm=True)

    def run(self, config: DockerRunConfig) -> DockerRunResult:
        with self._lock:
            if self._shutdown:
                raise RuntimeError(
                    "Docker runner is shut down; cannot start new containers"
                )

        client = self._client()
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

    def _client(self) -> docker.DockerClient:
        if self._base_url:
            return docker.DockerClient(base_url=self._base_url)
        return docker.from_env()

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


def colima_socket() -> str:
    """Return the Docker socket URL of the running Colima instance.

    Asks Colima itself rather than guessing the path, so ``COLIMA_PROFILE``,
    ``COLIMA_HOME`` and the XDG config fallback are all honoured.
    """
    try:
        proc = subprocess.run(
            ["colima", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "colima not found on PATH; install it with `brew install colima`"
        ) from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("`colima status` timed out") from None
    if proc.returncode != 0:
        raise RuntimeError("Colima is not running; start it with `colima start`")
    try:
        sock = json.loads(proc.stdout).get("docker_socket")
    except (json.JSONDecodeError, AttributeError):
        sock = None
    if not sock:
        raise RuntimeError(
            "Colima reports no Docker socket; "
            "start it with `colima start --runtime docker`"
        )
    return sock if "://" in sock else f"unix://{sock}"
