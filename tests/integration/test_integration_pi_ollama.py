"""End-to-end integration test: Pi agent with Ollama + LLM judge.

Requires:
- A running Docker daemon
- A running Ollama instance on localhost:11434 with qwen2.5-coder:1.5b pulled

Run with:
    pytest tests/integration/test_integration_pi_ollama.py -m integration -v
"""

from __future__ import annotations

import docker
import pytest

from tea import Agents
from tea.agent.agent_run import AgentRun
from tea.agent.pi import PiConfig


def _docker_available() -> bool:
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


def _ollama_available() -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(
            "http://localhost:11434/api/tags", timeout=3
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


_OLLAMA_BASE_URL = "http://host.docker.internal:11434/v1"
_OLLAMA_MODEL = "ollama/qwen2.5-coder:1.5b"

_skip_reason = (
    "Docker or Ollama (localhost:11434 with qwen2.5-coder:1.5b) not available"
)


@pytest.mark.integration
@pytest.mark.skipif(
    not (_docker_available() and _ollama_available()),
    reason=_skip_reason,
)
def test_pi_ollama_hello_world():
    """Pi agent runs a simple prompt via local Ollama and produces output."""
    cfg = PiConfig(_OLLAMA_MODEL, base_url=_OLLAMA_BASE_URL)
    run = Agents.Pi.with_model(cfg).prompt("Say 'hello world' and nothing else.").run()

    assert isinstance(run, AgentRun)
    assert len(run.raw) > 0, "raw output should not be empty"
    text_steps = [s for s in run.steps if s.type == "text"]
    assert len(text_steps) > 0, "expected at least one text step"
    combined = " ".join(s.content for s in text_steps).lower()
    assert "hello" in combined, f"expected 'hello' in output, got: {combined!r}"
    assert run.exit_code == 0, f"non-zero exit: {run.exit_code}\nstderr: {run.stderr}"


@pytest.mark.integration
@pytest.mark.skipif(
    not (_docker_available() and _ollama_available()),
    reason=_skip_reason,
)
def test_pi_ollama_with_deterministic_judge():
    """Pi agent answers a math question; result is verified programmatically."""
    cfg = PiConfig(_OLLAMA_MODEL, base_url=_OLLAMA_BASE_URL)
    run = (
        Agents.Pi.with_model(cfg)
        .prompt("What is 2 + 2? Respond with only the number, nothing else.")
        .run()
    )

    assert isinstance(run, AgentRun)
    assert run.exit_code == 0, f"non-zero exit: {run.exit_code}\nstderr: {run.stderr}"

    combined = " ".join(s.content for s in run.steps if s.type == "text")
    assert combined.strip(), "expected non-empty response from Pi"
    # The model should return "4" — allow some tolerance for trailing punctuation
    assert "4" in combined, f"expected '4' in response, got: {combined!r}"


@pytest.mark.integration
@pytest.mark.skipif(
    not (_docker_available() and _ollama_available()),
    reason=_skip_reason,
)
def test_pi_config_api_with_model_str_interface():
    """PiConfig is the correct type; PiHarness.with_model accepts it."""
    cfg = PiConfig(_OLLAMA_MODEL, base_url=_OLLAMA_BASE_URL)
    harness = Agents.Pi.with_model(cfg)
    # Ensure the spec is built correctly (host_network_access=True for Ollama)
    spec = harness._agent.build_spec("ping", timeout=30)
    assert spec.requirements.host_network_access is True
    assert len(spec.requirements.config_scopes) == 1
    assert spec.requirements.config_scopes[0].env_var == "PI_CODING_AGENT_DIR"
