from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field

from tea.infra import DockerRunConfig, run_in_docker

from .executor import ExecutionSpec, Executor, RawResult

_CONTAINER_WORKDIR = "/workspace"


@dataclass
class DockerProfile:
    image: str
    user: str | None = None
    setup_command: str | None = None
    env_overrides: dict[str, str] = field(default_factory=dict)


class DockerExecutor(Executor):
    def __init__(self, profile: DockerProfile) -> None:
        self._profile = profile

    def run(self, spec: ExecutionSpec, workdir: str | None) -> RawResult:
        volumes = {workdir: _CONTAINER_WORKDIR} if workdir else {}
        env = {**self._profile.env_overrides, **spec.env}
        extra_hosts: dict[str, str] = {}
        scope_tmps: list[str] = []

        if spec.requirements.host_network_access:
            extra_hosts["host.docker.internal"] = "host-gateway"

        for i, scope in enumerate(spec.requirements.config_scopes):
            tmp = tempfile.mkdtemp()
            scope_tmps.append(tmp)
            for rel_path, content in scope.files.items():
                abs_path = os.path.join(tmp, rel_path)
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "w", encoding="utf-8") as fh:
                    fh.write(content)
            os.chmod(tmp, 0o777)
            container_path = f"/tmp/tea-scope-{i}"
            volumes[tmp] = container_path
            env[scope.env_var] = container_path

        setup_parts = [
            p for p in [self._profile.setup_command, spec.setup_command] if p
        ]
        shell_cmd = (
            " && ".join(setup_parts + [spec.command]) if setup_parts else spec.command
        )

        try:
            config = DockerRunConfig(
                image=self._profile.image,
                command=["sh", "-c", shell_cmd],
                env=env,
                timeout=spec.timeout,
                volumes=volumes,
                container_workdir=_CONTAINER_WORKDIR if workdir else None,
                user=self._profile.user,
                extra_hosts=extra_hosts,
            )
            r = run_in_docker(config)
        finally:
            for tmp in scope_tmps:
                shutil.rmtree(tmp, ignore_errors=True)

        return RawResult(r.stdout, r.stderr, r.exit_code, r.duration_s)
