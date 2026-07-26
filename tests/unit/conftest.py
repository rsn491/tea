import pytest

from tea.agent._version import resolve_cli_version
from tea.infra import DockerRunResult


@pytest.fixture(autouse=True)
def _clear_cli_version_cache():
    """Isolate every test from ``resolve_cli_version``'s ``lru_cache``.

    The cache keys on the command/package/env-var triple, not on the env var's
    *value*, so a test that monkeypatches e.g. ``PI_VERSION`` would otherwise
    both read a stale entry and leave a poisoned one behind. Clearing on both
    sides of the yield keeps a failing assertion from cascading into unrelated
    tests — which manual ``cache_clear()`` calls could not, since the trailing
    one never runs when the assertion above it fails.
    """
    resolve_cli_version.cache_clear()
    yield
    resolve_cli_version.cache_clear()


def make_docker_result(
    stdout: str = "", stderr: str = "", exit_code: int = 0
) -> DockerRunResult:
    return DockerRunResult(stdout=stdout, stderr=stderr, exit_code=exit_code)
