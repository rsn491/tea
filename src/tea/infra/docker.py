from __future__ import annotations

import io
import time
from dataclasses import dataclass, field

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


def ensure_image(tag: str, dockerfile: str) -> None:
    client = docker.from_env()
    try:
        client.images.get(tag)
        return
    except docker.errors.ImageNotFound:
        pass
    client.images.build(fileobj=io.BytesIO(dockerfile.encode()), tag=tag, rm=True)


def run_in_docker(config: DockerRunConfig) -> DockerRunResult:
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
    stdout = ""
    stderr = ""
    exit_code = -1
    duration_s = 0.0
    try:
        exit_code = container.wait(timeout=config.timeout)["StatusCode"]
        duration_s = time.monotonic() - t0
        stdout = container.logs(stdout=True, stderr=False).decode(
            "utf-8", errors="replace"
        )
        stderr = container.logs(stdout=False, stderr=True).decode(
            "utf-8", errors="replace"
        )
    finally:
        container.remove(force=True)

    return DockerRunResult(
        stdout=stdout, stderr=stderr, exit_code=exit_code, duration_s=duration_s
    )
