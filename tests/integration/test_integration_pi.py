"""Integration test: runs Pi inside a Docker container.

Anthropic tests require ANTHROPIC_API_KEY. Ollama tests require a running
Ollama instance on localhost:11434 (no API key needed). Mock-provider tests
need only Docker: they spin up an in-process OpenAI-compatible server on the
host and point the containerized Pi at it via host.docker.internal, capturing
the request so skill discovery can be asserted deterministically.

Run with:
    pytest -m integration
"""

import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import docker
import pytest

from tea import Agents, ModelConfig
from tea.agent.agent_run import AgentRun

_SKILL_MD = (
    "---\n"
    "name: greet\n"
    "description: How to greet the user. Use whenever the user asks "
    "for a greeting.\n"
    "---\n"
    "# greet\n"
    "Whenever the user asks you to greet them, respond with exactly: "
    "SKILL_LOADED\n"
)


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
_SKIP_NO_DOCKER = pytest.mark.skipif(
    not _docker_available(), reason="Docker not available"
)


def _write_skill(tmp_path):
    skill_dir = tmp_path / ".pi" / "skills" / "greet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_SKILL_MD)


# ── Mock provider ─────────────────────────────────────────────────────────────


class _MockOpenAIServer:
    """OpenAI-compatible streaming mock that records request bodies.

    Binds 0.0.0.0 on an ephemeral port so the Docker container can reach it
    through host.docker.internal (the Pi harness maps it to host-gateway).
    """

    def __init__(self) -> None:
        self.requests: list[dict] = []
        capture = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8", errors="replace")
                try:
                    capture.append(json.loads(body))
                except json.JSONDecodeError:
                    capture.append({"raw": body})
                chunks = [
                    {
                        "id": "chatcmpl-mock",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "test-model",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "role": "assistant",
                                    "content": "MOCK_REPLY_OK",
                                },
                                "finish_reason": None,
                            }
                        ],
                    },
                    {
                        "id": "chatcmpl-mock",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "test-model",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 5,
                            "total_tokens": 15,
                        },
                    },
                ]
                payload = (
                    "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
                    + "data: [DONE]\n\n"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, fmt, *args):
                pass

        self._server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_MockOpenAIServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()

    def system_prompt(self) -> str:
        """Concatenated system-message content across captured requests."""
        parts = []
        for req in self.requests:
            for msg in req.get("messages", []):
                if msg.get("role") != "system":
                    continue
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict)
                    )
                parts.append(str(content))
        return "\n".join(parts)


# ── Mock-provider tests (need only Docker) ────────────────────────────────────


@pytest.mark.integration
@_SKIP_NO_DOCKER
def test_pi_end_to_end_with_mock_provider():
    """Full pipeline: Docker image, models.json setup, model call, JSON parse."""
    with _MockOpenAIServer() as mock:
        cfg = ModelConfig(
            "mock/test-model",
            base_url=f"http://host.docker.internal:{mock.port}/v1",
        )
        run = Agents.Pi.with_model(cfg).prompt("Say hello").run()

    assert isinstance(run, AgentRun)
    assert run.exit_code == 0, f"exit {run.exit_code}\nstderr: {run.stderr}"
    text_steps = [s.content for s in run.steps if s.type == "text"]
    assert "MOCK_REPLY_OK" in " ".join(text_steps), (
        f"mock reply missing from steps; raw: {run.raw[:2000]!r}"
    )
    assert len(mock.requests) == 1, "expected exactly one model request"


@pytest.mark.integration
@_SKIP_NO_DOCKER
def test_pi_surfaces_model_call_failure():
    """A failed model call must not look like a clean run.

    pi's JSON print mode exits 0 even when the provider is unreachable, so the
    harness has to detect the stopReason=error events and surface a non-zero
    exit. Point the provider at a closed port to force the failure end-to-end.
    """
    cfg = ModelConfig(
        "mock/test-model",
        # 9 is the discard port — reliably refuses inside the container.
        base_url="http://host.docker.internal:9/v1",
    )
    run = Agents.Pi.with_model(cfg).prompt("Say hello").run()

    assert isinstance(run, AgentRun)
    assert run.exit_code != 0, (
        f"unreachable provider must surface as failure; raw: {run.raw[:2000]!r}"
    )
    assert run.error, "the error message should be captured"


@pytest.mark.integration
@_SKIP_NO_DOCKER
def test_pi_skill_reaches_system_prompt_via_native_discovery(tmp_path):
    """The installed skill must appear in the system prompt Pi sends the model.

    This asserts the whole native-discovery chain deterministically: the
    harness copies the skill into /home/node/.pi/agent/skills/ (always
    trusted), Pi discovers it at startup, and advertises it to the model in
    an <available_skills> block. Project-local /workspace/.pi/skills would be
    ignored by Pi in --print mode (untrusted, no UI to grant trust), so the
    system prompt must reference the user-scope copy.
    """
    _write_skill(tmp_path)
    with _MockOpenAIServer() as mock:
        cfg = ModelConfig(
            "mock/test-model",
            base_url=f"http://host.docker.internal:{mock.port}/v1",
        )
        run = (
            Agents.Pi.with_model(cfg)
            .prompt("Greet me using the greet skill.")
            .workdir(str(tmp_path))
            .skills_from([".pi/skills"])
            .run()
        )

    assert run.exit_code == 0, f"exit {run.exit_code}\nstderr: {run.stderr}"
    system = mock.system_prompt()
    assert "<available_skills>" in system, (
        f"no skills block in system prompt: {system[-2000:]!r}"
    )
    assert "greet" in system
    assert "How to greet the user" in system, "skill description missing"
    assert "/home/node/.pi/agent/skills/greet/SKILL.md" in system, (
        "skill not loaded from Pi's native user-scope path"
    )
    # Native discovery replaced the old prompt-preamble approach: the user
    # message must be exactly the prompt, with no injected skill listing.
    user_texts = []
    for req in mock.requests:
        for msg in req.get("messages", []):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict)
                    )
                user_texts.append(str(content))
    assert user_texts == ["Greet me using the greet skill."]


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
    _write_skill(tmp_path)

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
    """The pipeline stays healthy when skills are installed for an Ollama run.

    Small local models follow skill instructions unreliably, so this test only
    asserts pipeline health; deterministic skill-discovery coverage lives in
    test_pi_skill_reaches_system_prompt_via_native_discovery above.
    """
    _write_skill(tmp_path)

    run = (
        Agents.Pi.with_model(_OLLAMA_MODEL)
        .prompt("Greet me using the greet skill.")
        .workdir(str(tmp_path))
        .skills_from([".pi/skills"])
        .run()
    )

    assert isinstance(run, AgentRun)
    assert run.exit_code == 0, f"exit {run.exit_code}\nstderr: {run.stderr}"
    assert len(run.steps) > 0, "expected at least one step from the agent"
