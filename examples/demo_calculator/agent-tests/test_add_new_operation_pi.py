"""Skill-eval test for the Pi agent against the calculator example.

Mirrors test_add_new_operation.py (Claude Code variant) using Pi as the
agent backend. Pi has no default model and no OAuth path, so the three
MODEL_PROVIDER_* env vars are required (set them in a local .env):

    MODEL_PROVIDER_MODEL    e.g. ollama/qwen2.5-coder:1.5b
    MODEL_PROVIDER_BASE_URL e.g. http://host.docker.internal:11434
    MODEL_PROVIDER_KEY      provider api key (or "local" for unauthenticated)

Pi does not emit skill-invocation events, so this test asserts on the
unified diff via check_diff_added rather than check_skill_used.
"""

import os

from tea import Agents, check, check_diff_added
from tea.agent.pi import PiConfig
from tea.runner import iterations

_MODEL = os.environ["MODEL_PROVIDER_MODEL"]
_BASE_URL = os.environ["MODEL_PROVIDER_BASE_URL"].rstrip("/") + "/v1"
_API_KEY_ENV = "MODEL_PROVIDER_KEY"

_pi = Agents.Pi.with_model(
    PiConfig(_MODEL, api_key_env=_API_KEY_ENV, base_url=_BASE_URL)
)


@iterations(2)
def test_pi_add_minus_operation():
    run = (
        _pi.prompt("Add 'minus' operation support to the calculator", timeout=600)
        .workdir("examples/demo_calculator")
        .run()
    )

    check("pi exited cleanly", run.exit_code == 0)
    check_diff_added(run, "calculator.py", "minus")
    check_diff_added(run, "test_calculator.py", "test_minus")
    check_diff_added(run, "README.md", "minus")
