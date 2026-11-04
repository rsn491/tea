"""Benchmark test: one Pi run against the mock LiteLLM endpoint.

See benchmarks/README.md. BENCH_WORKDIR picks the workdir to copy into the
container (default: examples/demo_calculator).
"""

import os

from tea import Agents, PiConfig, check

_pi = Agents.Pi.with_model(
    PiConfig(
        "litellm/bench",
        base_url=os.environ.get(
            "BENCH_BASE_URL", "http://host.docker.internal:4000/v1"
        ),
    )
)
_WORKDIR = os.environ.get("BENCH_WORKDIR", "examples/demo_calculator")


def test_bench():
    run = _pi.prompt("Say hello world and nothing else.").workdir(_WORKDIR).run()

    check("pi exited cleanly", run.exit_code == 0)
    check("mock reply received", "hello" in run.transcript.lower())
