import pytest
from unittest.mock import patch, MagicMock
from harntest.infra import DockerRunResult


@pytest.fixture
def mock_docker():
    with patch("harntest.infra.run_in_docker") as mock:
        yield mock


def make_docker_result(
    stdout: str = "", stderr: str = "", exit_code: int = 0
) -> DockerRunResult:
    return DockerRunResult(stdout=stdout, stderr=stderr, exit_code=exit_code)
