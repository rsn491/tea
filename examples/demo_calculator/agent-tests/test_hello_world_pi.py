"""Minimal Pi sanity-check: confirms the pipeline works end-to-end without
asking the model to edit any code — safe to run against a tiny local model
in CI. Requires the same three MODEL_PROVIDER_* env vars as
test_add_new_operation_pi.py (set them in a local .env to run manually):

    MODEL_PROVIDER_MODEL    e.g. ollama/qwen2.5-coder:1.5b
    MODEL_PROVIDER_BASE_URL e.g. http://host.docker.internal:11434
    MODEL_PROVIDER_KEY      provider api key (or "local" for unauthenticated)
"""

import os

from tea import Agents, ModelConfig, check

_MODEL = os.environ["MODEL_PROVIDER_MODEL"]
_BASE_URL = os.environ["MODEL_PROVIDER_BASE_URL"].rstrip("/") + "/v1"
_API_KEY_ENV = "MODEL_PROVIDER_KEY"

_pi = Agents.Pi.with_model(
    ModelConfig(_MODEL, api_key_env=_API_KEY_ENV, base_url=_BASE_URL)
)


def test_pi_hello_world():
    run = _pi.prompt("Say hello world and nothing else.").run()

    check("pi exited cleanly", run.exit_code == 0)
    check("no model error", run.error is None)
    check("greeting present", "hello" in run.transcript.lower())
