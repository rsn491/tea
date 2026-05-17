from __future__ import annotations

from tea.infra import DockerRunConfig, run_in_docker

from .executor import DockerSpec, Executor, RawResult

_CONTAINER_WORKDIR = "/workspace"


class DockerExecutor(Executor):
    def run(self, spec: DockerSpec, workdir: str | None) -> RawResult:
        volumes = {workdir: _CONTAINER_WORKDIR} if workdir else {}
        volumes.update(spec.requirements.extra_mounts)
        container_cwd = _CONTAINER_WORKDIR if workdir else None
        extra_hosts: dict[str, str] = {}
        if spec.requirements.host_network_access:
            extra_hosts["host.docker.internal"] = "host-gateway"
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
            extra_hosts=extra_hosts,
        )
        r = run_in_docker(config)
        return RawResult(r.stdout, r.stderr, r.exit_code, r.duration_s)
