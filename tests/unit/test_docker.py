from unittest.mock import MagicMock, patch

import pytest

from tea.infra import Docker, DockerRunConfig, DockerRunResult


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
def test_client_is_reused_across_runs_and_image_checks(mock_docker_module):
    client = mock_docker_module.from_env.return_value
    client.containers.run.side_effect = lambda *a, **k: _make_container()
    runner = Docker()

    config = DockerRunConfig(image="node:22", command=["echo", "hi"])
    runner.create_image("node:22", "FROM node:22\n")
    runner.run(config)
    runner.run(config)

    assert mock_docker_module.from_env.call_count == 1


@patch("tea.infra.docker.docker")
def test_create_image_checks_each_tag_once(mock_docker_module):
    client = mock_docker_module.from_env.return_value
    runner = Docker()

    runner.create_image("tea:1", "FROM node:22\n")
    runner.create_image("tea:1", "FROM node:22\n")
    runner.create_image("tea:2", "FROM node:22\n")

    assert [c.args[0] for c in client.images.get.call_args_list] == ["tea:1", "tea:2"]
    client.images.build.assert_not_called()


@patch("tea.infra.docker.docker")
def test_create_image_builds_missing_tag_once(mock_docker_module):
    class ImageNotFound(Exception):
        pass

    mock_docker_module.errors.ImageNotFound = ImageNotFound
    client = mock_docker_module.from_env.return_value
    client.images.get.side_effect = ImageNotFound
    runner = Docker()

    runner.create_image("tea:1", "FROM node:22\n")
    runner.create_image("tea:1", "FROM node:22\n")

    client.images.build.assert_called_once()
    assert client.images.build.call_args.kwargs["tag"] == "tea:1"
