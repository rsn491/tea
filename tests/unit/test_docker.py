from unittest.mock import MagicMock, patch

import pytest

from tea.infra import Docker, DockerRunConfig, DockerRunResult
from tea.infra.docker import colima_socket


def _make_container(stdout=b"out", stderr=b"err", exit_code=0):
    container = MagicMock()
    container.wait.return_value = {"StatusCode": exit_code}
    container.logs.side_effect = lambda stdout=True, stderr=False: (
        b"out" if stdout else b"err"
    )
    return container


@patch("tea.infra.docker.docker")
def test_run_returns_result(mock_docker_module):
    container = _make_container()
    mock_docker_module.from_env.return_value.containers.run.return_value = container

    config = DockerRunConfig(image="node:22", command=["echo", "hi"])
    result = Docker().run(config)

    assert isinstance(result, DockerRunResult)
    assert result.exit_code == 0
    assert result.stdout == "out"
    assert result.stderr == "err"


@patch("tea.infra.docker.docker")
def test_run_uses_detach_and_no_remove(mock_docker_module):
    container = _make_container()
    mock_docker_module.from_env.return_value.containers.run.return_value = container

    config = DockerRunConfig(image="node:22", command=["sh", "-c", "echo hello"])
    Docker().run(config)

    call_kwargs = mock_docker_module.from_env.return_value.containers.run.call_args
    assert call_kwargs.kwargs.get("detach") is True
    assert call_kwargs.kwargs.get("remove") is False


@patch("tea.infra.docker.docker")
def test_container_removed_after_run(mock_docker_module):
    container = _make_container()
    mock_docker_module.from_env.return_value.containers.run.return_value = container

    config = DockerRunConfig(image="node:22", command=["echo", "hi"])
    Docker().run(config)

    container.remove.assert_called_once_with(force=True)


@patch("tea.infra.docker.docker")
def test_container_removed_on_timeout(mock_docker_module):
    container = MagicMock()
    container.wait.side_effect = Exception("timeout")
    mock_docker_module.from_env.return_value.containers.run.return_value = container

    config = DockerRunConfig(image="node:22", command=["sleep", "999"], timeout=1)
    with pytest.raises(Exception):
        Docker().run(config)

    container.remove.assert_called_once_with(force=True)


@patch("tea.infra.docker.docker")
def test_run_raises_after_shutdown(mock_docker_module):
    runner = Docker()
    runner.shutdown()

    config = DockerRunConfig(image="node:22", command=["echo", "hi"])
    with pytest.raises(RuntimeError, match="shut down"):
        runner.run(config)


@patch("tea.infra.docker.docker")
def test_shared_returns_singleton_when_no_context(mock_docker_module):
    Docker._singleton = None  # reset for test isolation
    a = Docker.get()
    b = Docker.get()
    assert a is b


@patch("tea.infra.docker.docker")
def test_client_uses_base_url_when_set(mock_docker_module):
    Docker(base_url="unix:///tmp/colima.sock")._client()
    mock_docker_module.DockerClient.assert_called_once_with(
        base_url="unix:///tmp/colima.sock"
    )
    mock_docker_module.from_env.assert_not_called()


@patch("tea.infra.docker.docker")
def test_client_uses_env_by_default(mock_docker_module):
    Docker()._client()
    mock_docker_module.from_env.assert_called_once_with()
    mock_docker_module.DockerClient.assert_not_called()


def _colima_status(returncode=0, stdout=""):
    return MagicMock(returncode=returncode, stdout=stdout)


@patch("tea.infra.docker.subprocess.run")
def test_colima_socket_reads_status(mock_run):
    mock_run.return_value = _colima_status(
        stdout='{"docker_socket": "unix:///Users/me/.colima/default/docker.sock"}'
    )
    assert colima_socket() == "unix:///Users/me/.colima/default/docker.sock"


@patch("tea.infra.docker.subprocess.run")
def test_colima_socket_adds_scheme_to_bare_path(mock_run):
    mock_run.return_value = _colima_status(
        stdout='{"docker_socket": "/Users/me/.colima/default/docker.sock"}'
    )
    assert colima_socket() == "unix:///Users/me/.colima/default/docker.sock"


@patch("tea.infra.docker.subprocess.run", side_effect=FileNotFoundError)
def test_colima_socket_missing_binary(mock_run):
    with pytest.raises(RuntimeError, match="brew install colima"):
        colima_socket()


@patch("tea.infra.docker.subprocess.run")
def test_colima_socket_not_running(mock_run):
    mock_run.return_value = _colima_status(returncode=1)
    with pytest.raises(RuntimeError, match="colima start"):
        colima_socket()


@patch("tea.infra.docker.subprocess.run")
def test_colima_socket_without_docker_runtime(mock_run):
    mock_run.return_value = _colima_status(stdout='{"runtime": "containerd"}')
    with pytest.raises(RuntimeError, match="--runtime docker"):
        colima_socket()


@patch("tea.infra.docker.colima_socket", return_value="unix:///tmp/colima.sock")
def test_use_colima_replaces_singleton(mock_socket):
    Docker._singleton = None
    try:
        Docker.use_colima()
        assert Docker.get()._base_url == "unix:///tmp/colima.sock"
    finally:
        Docker._singleton = None
