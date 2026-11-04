# Benchmarking tea

Black-box benchmarks of a single tea test execution, using off-the-shelf tools
only — no benchmark harness code.

| Tool | Role |
|---|---|
| [hyperfine](https://github.com/sharkdp/hyperfine) | Wall-clock timing, statistics, A/B comparison, parameter scans |
| [LiteLLM proxy](https://docs.litellm.ai/docs/proxy/quick_start) | Mock OpenAI-compatible model: instant, deterministic replies |
| [py-spy](https://github.com/benfred/py-spy) | Sampling profiler: shows where tea's own time goes, no code changes |

The benchmark uses the Pi agent because it accepts a custom `base_url`, so it
can talk to the mock without any change to tea. A run still goes through the
full per-test path: workdir copy → change snapshot → image check → container
start + Node CLI cold start → logs → parse → diff → cleanup.

## Setup

```bash
# Mock model on :4000 (no API key needed)
docker run -d --name tea-bench-llm -p 4000:4000 \
  -v "$PWD/benchmarks/litellm.yaml:/config.yaml" \
  ghcr.io/berriai/litellm:main-stable --config /config.yaml

export PI_VERSION=<pinned version>   # fixed image tag, skips version probing
tea benchmarks/test_bench.py          # warm-up: builds the image once
```

`BENCH_WORKDIR` selects the workdir (default `examples/demo_calculator`). Use a
large real checkout (e.g. a repo with `node_modules`) for the I/O-heavy case.
Set `TMPDIR=/dev/shm` to put the workdir copy on tmpfs.

## Measurements

```bash
# Floors: Python startup, and a bare container
hyperfine --warmup 3 'tea --help' "docker run --rm tea-pi:$PI_VERSION true"

# Per-test cost: the slope (T21 - T1) / 20 excludes process startup
hyperfine --warmup 1 -P n 1 21 -D 10 \
  'tea benchmarks/test_bench.py -n {n}' --export-markdown bench.md

# A/B against main (two venvs with `pip install -e .`)
hyperfine --warmup 3 --runs 20 \
  -n main   '../tea-main/.venv/bin/tea benchmarks/test_bench.py' \
  -n branch '.venv/bin/tea benchmarks/test_bench.py'

# Cold page cache (root)
hyperfine --prepare 'sync; echo 3 | sudo tee /proc/sys/vm/drop_caches' \
  'tea benchmarks/test_bench.py'

# Where the time goes
py-spy record -o tea.svg -- tea benchmarks/test_bench.py -n 10
```
