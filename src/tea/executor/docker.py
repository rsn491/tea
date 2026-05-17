from __future__ import annotations

from tea.infra import DockerRunConfig, run_in_docker
from tea.infra.docker import ensure_image

from .executor import DockerSpec, Executor, RawResult

_CONTAINER_WORKDIR = "/workspace"


class DockerExecutor(Executor):
    def run(self, spec: DockerSpec, workdir: str | None) -> RawResult:
        if spec.dockerfile:
            ensure_image(spec.image, spec.dockerfile)
        volumes = {workdir: _CONTAINER_WORKDIR} if workdir else {}
        volumes.update(spec.extra_volumes)
        container_cwd = _CONTAINER_WORKDIR if workdir else None
        shell_cmd = (
            f"{spec.setup_command} && {spec.command}"
            if spec.setup_command
            else spec.command
        )
        config = DockerRunConfig(
            image=spec.image,
            command=["sh", "-c", shell_cmd],
            env=spec.env,
            timeout=spec.timeout,
            volumes=volumes,
            container_workdir=container_cwd,
            user=spec.user,
            extra_hosts=spec.extra_hosts,
        )
        r = run_in_docker(config)
        return RawResult(r.stdout, r.stderr, r.exit_code, r.duration_s)
