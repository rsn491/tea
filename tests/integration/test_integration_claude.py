"""Integration test: runs Claude Code inside a Docker container.

Requires:
- A running Docker daemon
- ANTHROPIC_API_KEY set in the host environment

Run with:
    pytest -m integration
"""

import os

import docker
import pytest

from tea import Agents
from tea.agent.agent_run import AgentRun, StepType


def _docker_available() -> bool:
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(
    (not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")) or (not _docker_available()),
    reason="CLAUDE_CODE_OAUTH_TOKEN not set or Docker not available",
)
def test_claude_code_hello_world():
    run = Agents.ClaudeCode.prompt("Say hello world and nothing else.").run()

    assert isinstance(run, AgentRun)
    assert isinstance(run.raw, str)
    assert len(run.raw) > 0, "raw output should not be empty"

    assert isinstance(run.steps, list)
    assert isinstance(run.tools, list)
    assert isinstance(run.skills, list)

    # The agent should have produced at least one text step
    text_steps = [s for s in run.steps if s.type == StepType.TEXT]
    assert len(text_steps) > 0, "expected at least one text step"

    # The combined text content should mention "hello"
    combined = " ".join(s.content for s in text_steps).lower()
    assert "hello" in combined, f"expected 'hello' in output, got: {combined!r}"

    # exit_code 0 means the CLI succeeded
    assert run.exit_code == 0, (
        f"non-zero exit code: {run.exit_code}\nstderr: {run.stderr}"
    )


@pytest.mark.integration
@pytest.mark.skipif(
    (not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")) or (not _docker_available()),
    reason="CLAUDE_CODE_OAUTH_TOKEN not set or Docker not available",
)
def test_claude_code_prompt_with_null_byte():
    # A prompt containing a null byte (e.g. from binary content in a diff) must
    # not crash the container: env vars can't hold null bytes, so the prompt is
    # sanitized before being passed. Before the fix Docker rejected the run with
    # 'invalid environment variable ... value contains nul byte'.
    run = Agents.ClaudeCode.prompt(
        "Say hello world and nothing else.\x00 Ignore this null byte."
    ).run()

    assert run.exit_code == 0, (
        f"non-zero exit code: {run.exit_code}\nstderr: {run.stderr}"
    )
