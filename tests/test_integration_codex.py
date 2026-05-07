"""Integration test: runs Codex inside a Docker container.

Requires:
- A running Docker daemon
- OPENAI_API_KEY set in the host environment

Run with:
    pytest -m integration
"""
import os
import pytest

from harntest import Agent
from harntest.models import AgentRun


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
def test_codex_hello_world():
    run = Agent.Codex.prompt("Say hello world and nothing else.")

    assert isinstance(run, AgentRun)
    assert isinstance(run.raw, str)
    assert len(run.raw) > 0, "raw output should not be empty"

    assert isinstance(run.steps, list)
    assert isinstance(run.tools, list)
    assert isinstance(run.skills, list)

    # The agent should have produced at least one step
    assert len(run.steps) > 0, "expected at least one step"

    # The combined content should mention "hello"
    combined = " ".join(s.content for s in run.steps).lower()
    assert "hello" in combined, f"expected 'hello' in output, got: {combined!r}"

    # exit_code 0 means the CLI succeeded
    assert run.exit_code == 0, f"non-zero exit code: {run.exit_code}\nstderr: {run.stderr}"
