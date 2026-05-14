from unittest.mock import MagicMock, patch

import pytest

from harntest.infra import DockerRunConfig, DockerRunResult, run_in_docker


def _make_container(stdout=b"out", stderr=b"err", exit_code=0):
    container = MagicMock()
    container.wait.return_value = {"StatusCode": exit_code}
    container.logs.side_effect = lambda stdout=True, stderr=False: (
        b"out" if stdout else b"err"
    )
    return container


@patch("harntest.infra.docker.docker")
def test_run_in_docker_returns_result(mock_docker_module):
    container = _make_container()
    mock_docker_module.from_env.return_value.containers.run.return_value = container

    config = DockerRunConfig(image="node:22", command=["echo", "hi"])
    result = run_in_docker(config)

    assert isinstance(result, DockerRunResult)
    assert result.exit_code == 0
    assert result.stdout == "out"
    assert result.stderr == "err"


@patch("harntest.infra.docker.docker")
def test_run_in_docker_uses_detach_and_no_remove(mock_docker_module):
    container = _make_container()
    mock_docker_module.from_env.return_value.containers.run.return_value = container

    config = DockerRunConfig(image="node:22", command=["sh", "-c", "echo hello"])
    run_in_docker(config)

    call_kwargs = mock_docker_module.from_env.return_value.containers.run.call_args
    assert call_kwargs.kwargs.get("detach") is True
    assert call_kwargs.kwargs.get("remove") is False


@patch("harntest.infra.docker.docker")
def test_container_removed_after_run(mock_docker_module):
    container = _make_container()
    mock_docker_module.from_env.return_value.containers.run.return_value = container

    config = DockerRunConfig(image="node:22", command=["echo", "hi"])
    run_in_docker(config)

    container.remove.assert_called_once_with(force=True)


@patch("harntest.infra.docker.docker")
def test_container_removed_on_timeout(mock_docker_module):
    container = MagicMock()
    container.wait.side_effect = Exception("timeout")
    mock_docker_module.from_env.return_value.containers.run.return_value = container

    config = DockerRunConfig(image="node:22", command=["sleep", "999"], timeout=1)
    with pytest.raises(Exception):
        run_in_docker(config)

    container.remove.assert_called_once_with(force=True)
