from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from tea.infra import Docker, DockerRunConfig

from .executor import WORKDIR_MOUNT, ExecutionSpec, Executor, RawResult


@dataclass
class DockerProfile:
    """Static per-agent Docker knowledge: how to build and enter the container.

    Everything here is independent of any single run — the dynamic, per-run
    pieces (command, env, requirements) travel in the ``ExecutionSpec``.
    """

    image: str
    dockerfile: str | None = None  # when set, the image is built on first use
    user: str | None = None
    env_overrides: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.image:
            raise ValueError("DockerProfile.image must be a non-empty image tag")


class DockerExecutor(Executor):
    """Runs an ``ExecutionSpec`` inside a Docker container.

    ``profile`` may be a ``DockerProfile`` or a zero-arg callable returning
    one. Agents pass a callable so version resolution (which probes the CLI /
    npm) happens lazily at run time instead of import time.
    """

    def __init__(
        self,
        profile: DockerProfile | Callable[[], DockerProfile],
        docker: Docker | None = None,
    ) -> None:
        self._profile = profile
        self._docker = docker if docker is not None else Docker.get()

    def run(self, spec: ExecutionSpec, workdir: str | None) -> RawResult:
        profile = self._profile() if callable(self._profile) else self._profile
        if profile.dockerfile:
            self._docker.create_image(profile.image, profile.dockerfile)

        volumes = {workdir: WORKDIR_MOUNT} if workdir else {}
        volumes.update(spec.requirements.extra_mounts)
        env = {**profile.env_overrides, **spec.env}
        extra_hosts: dict[str, str] = {}
        if spec.requirements.host_network_access:
            extra_hosts["host.docker.internal"] = "host-gateway"

        shell_cmd = (
            f"{spec.setup_command} && {spec.command}"
            if spec.setup_command
            else spec.command
        )

        config = DockerRunConfig(
            image=profile.image,
            command=["sh", "-c", shell_cmd],
            env=env,
            timeout=spec.timeout,
            volumes=volumes,
            container_workdir=WORKDIR_MOUNT if workdir else None,
            user=profile.user,
            extra_hosts=extra_hosts,
        )
        r = self._docker.run(config)

        return RawResult(r.stdout, r.stderr, r.exit_code, r.duration_s)
