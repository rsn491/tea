from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Callable

from tea.infra import Docker, DockerRunConfig

from .executor import ExecutionSpec, Executor, RawResult

_CONTAINER_WORKDIR = "/workspace"


@dataclass
class DockerProfile:
    """Static per-agent Docker knowledge: how to build and enter the container.

    Everything here is independent of any single run — the dynamic, per-run
    pieces (command, env, config scopes) travel in the ``ExecutionSpec``.
    """

    image: str
    dockerfile: str | None = None  # when set, the image is built on first use
    user: str | None = None
    setup_command: str | None = None  # runs before the spec's setup/command
    env_overrides: dict[str, str] = field(default_factory=dict)


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

        volumes = {workdir: _CONTAINER_WORKDIR} if workdir else {}
        volumes.update(spec.requirements.extra_mounts)
        env = {**profile.env_overrides, **spec.env}
        extra_hosts: dict[str, str] = {}
        if spec.requirements.host_network_access:
            extra_hosts["host.docker.internal"] = "host-gateway"

        scope_tmps: list[str] = []
        try:
            for i, scope in enumerate(spec.requirements.config_scopes):
                tmp = tempfile.mkdtemp(prefix="tea-scope-")
                scope_tmps.append(tmp)
                _write_scope_files(tmp, scope.files)
                # The container user (e.g. "node") differs from the host user
                # that created the dir; the CLI must be able to write into its
                # config dir (locks, caches, session files).
                os.chmod(tmp, 0o777)
                container_path = f"/tmp/tea-scope-{i}"
                volumes[tmp] = container_path
                env[scope.env_var] = container_path

            setup_parts = [p for p in (profile.setup_command, spec.setup_command) if p]
            shell_cmd = " && ".join([*setup_parts, spec.command])

            config = DockerRunConfig(
                image=profile.image,
                command=["sh", "-c", shell_cmd],
                env=env,
                timeout=spec.timeout,
                volumes=volumes,
                container_workdir=_CONTAINER_WORKDIR if workdir else None,
                user=profile.user,
                extra_hosts=extra_hosts,
            )
            r = self._docker.run(config)
        finally:
            for tmp in scope_tmps:
                shutil.rmtree(tmp, ignore_errors=True)

        return RawResult(r.stdout, r.stderr, r.exit_code, r.duration_s)


def _write_scope_files(root: str, files: dict[str, str]) -> None:
    for rel_path, content in files.items():
        abs_path = os.path.normpath(os.path.join(root, rel_path))
        if not abs_path.startswith(root + os.sep):
            raise ValueError(
                f"ConfigScope file path {rel_path!r} escapes its scope directory"
            )
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content)
