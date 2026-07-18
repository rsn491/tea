from tea.infra import DockerRunResult


def make_docker_result(
    stdout: str = "", stderr: str = "", exit_code: int = 0
) -> DockerRunResult:
    return DockerRunResult(stdout=stdout, stderr=stderr, exit_code=exit_code)
