"""Integration test: runs Pi inside a Docker container.

Anthropic tests require ANTHROPIC_API_KEY. Ollama tests require a running
Ollama instance on localhost:11434 (no API key needed).

Run with:
    pytest -m integration
"""

import os
import urllib.request

import docker
import pytest

from tea import Agents, ModelConfig
from tea.agent.agent_run import AgentRun


def _docker_available() -> bool:
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def _ollama_available() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        return True
    except Exception:
        return False


_ANTHROPIC_MODEL = ModelConfig(
    "anthropic/claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY"
)
_OLLAMA_MODEL = ModelConfig(
    "ollama/llama3.2:latest",
    base_url="http://host.docker.internal:11434/v1",
)

_SKIP_ANTHROPIC = pytest.mark.skipif(
    (not os.environ.get("ANTHROPIC_API_KEY")) or (not _docker_available()),
    reason="ANTHROPIC_API_KEY not set or Docker not available",
)
_SKIP_OLLAMA = pytest.mark.skipif(
    not _docker_available() or not _ollama_available(),
    reason="Docker not available or Ollama not running on localhost:11434",
)


# ── Anthropic tests ───────────────────────────────────────────────────────────


@pytest.mark.integration
@_SKIP_ANTHROPIC
def test_pi_hello_world():
    run = (
        Agents.Pi.with_model(_ANTHROPIC_MODEL)
        .prompt("Say hello world and nothing else.")
        .run()
    )

    assert isinstance(run, AgentRun)
    assert len(run.raw) > 0, "raw output should not be empty"

    text_steps = [s for s in run.steps if s.type == "text"]
    assert len(text_steps) > 0, "expected at least one text step"

    combined = " ".join(s.content for s in text_steps).lower()
    assert "hello" in combined, f"expected 'hello' in output, got: {combined!r}"
    assert run.exit_code == 0, f"exit {run.exit_code}\nstderr: {run.stderr}"


@pytest.mark.integration
@_SKIP_ANTHROPIC
def test_pi_skill_is_loaded(tmp_path):
    """Pi copies a SKILL.md into its native path and the model uses it."""
    skill_dir = tmp_path / ".pi" / "skills" / "greet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# greet\nWhenever the user asks you to greet them, "
        "respond with exactly: SKILL_LOADED\n"
    )

    run = (
        Agents.Pi.with_model(_ANTHROPIC_MODEL)
        .prompt("Greet me using the greet skill.")
        .workdir(str(tmp_path))
        .skills_from([".pi/skills"])
        .run()
    )

    assert isinstance(run, AgentRun)
    assert run.exit_code == 0, f"exit {run.exit_code}\nstderr: {run.stderr}"
    combined = " ".join(s.content for s in run.steps if s.type == "text").upper()
    assert "SKILL_LOADED" in combined, f"skill not used; output: {combined!r}"


# ── Ollama tests ──────────────────────────────────────────────────────────────


@pytest.mark.integration
@_SKIP_OLLAMA
def test_pi_hello_world_ollama():
    """Pi runs a prompt end-to-end through Docker against a local Ollama model."""
    run = (
        Agents.Pi.with_model(_OLLAMA_MODEL)
        .prompt("Say hello world and nothing else.")
        .run()
    )

    assert isinstance(run, AgentRun)
    assert isinstance(run.raw, str)
    assert len(run.raw) > 0, "raw output should not be empty"

    assert isinstance(run.steps, list)
    assert isinstance(run.tools, list)
    assert isinstance(run.skills, list)

    # Local small models may respond with tool-call JSON rather than plain text;
    # we verify the pipeline ran end-to-end (steps produced, clean exit).
    assert len(run.steps) > 0, "expected at least one step from the agent"
    assert run.exit_code == 0, f"exit {run.exit_code}\nstderr: {run.stderr}"


@pytest.mark.integration
@_SKIP_OLLAMA
def test_pi_skill_is_loaded_ollama(tmp_path):
    """Pi copies a SKILL.md into its native discovery path and the model sees it."""
    skill_dir = tmp_path / ".pi" / "skills" / "greet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# greet\nA tool for greeting. Call it when asked to greet.\n"
    )

    run = (
        Agents.Pi.with_model(_OLLAMA_MODEL)
        .prompt("Greet me using the greet skill.")
        .workdir(str(tmp_path))
        .skills_from([".pi/skills"])
        .run()
    )

    assert isinstance(run, AgentRun)
    assert run.exit_code == 0, f"exit {run.exit_code}\nstderr: {run.stderr}"

    # Pi discovered and invoked the skill when its name appears in any step output.
    combined = " ".join(s.content for s in run.steps).lower()
    assert "greet" in combined, (
        f"expected 'greet' skill to appear in agent output; got: {combined!r}"
    )
