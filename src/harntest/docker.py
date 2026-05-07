from __future__ import annotations

from dataclasses import dataclass, field

import docker


@dataclass
class DockerRunConfig:
    image: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    timeout: int = 300


@dataclass
class DockerRunResult:
    stdout: str
    stderr: str
    exit_code: int


def run_in_docker(config: DockerRunConfig) -> DockerRunResult:
    client = docker.from_env()
    container = client.containers.run(
        config.image,
        config.command,
        environment=config.env or None,
        detach=True,
        remove=False,
    )
    try:
        exit_code = container.wait(timeout=config.timeout)["StatusCode"]
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
    finally:
        container.remove(force=True)

    return DockerRunResult(stdout=stdout, stderr=stderr, exit_code=exit_code)
