# tea — working in this project

## Before committing or pushing

Pre-commit hooks handle linting and tests (see `.pre-commit-config.yaml`).
They must pass before committing — the pipeline enforces the same checks.

```bash
pre-commit run --all-files
```

## Development setup

```bash
pip install -e ".[dev]"
pre-commit install          # wire hooks into git so they run on every commit
```

## Running tests

```bash
# Unit tests only (fast, no external deps)
pytest tests/unit -q

# Integration tests (require Docker and CLAUDE_CODE_OAUTH_TOKEN)
pytest tests/integration -q
```

## Project structure

```
src/tea/
├── agent/          # Agent ABC, ClaudeCode adapter, AgentRun data model
├── executor/       # Executor ABC, DockerExecutor adapter
├── judge/          # Judge ABC, PydanticAIJudge adapter, JudgeResult
├── infra/          # docker-py wrapper
├── tui/            # terminal output
├── checkers.py     # check() + skill/tool/file used·not_used·changed, diff_added/removed, judge_diff/run
└── runner.py       # test discovery and execution

tests/unit/         # no Docker, no API keys — always runnable
tests/integration/  # require Docker + CLAUDE_CODE_OAUTH_TOKEN
examples/           # runnable example tests
```

## Architecture

The codebase has two independent subsystems: the **harness** (runs the agent)
and the **judge** (grades the result). They share no code and are configured
separately — you can swap either without touching the other.

### Harness

Glues an `Agent` and an `Executor` together to produce an `AgentRun`:

```
Harness
├── Agent (ABC)        agent/agent.py
│    └── ClaudeCode    agent/claude_code.py   — builds the CLI command, parses stream-json output
└── Executor (ABC)     executor/executor.py
     └── DockerExecutor executor/docker_executor.py — runs the command in a container (per-agent DockerProfile), returns stdout/stderr
```

`Agent.build_spec()` returns an `ExecutionSpec`; `Executor.run()` consumes it and
returns a `RawResult`; `Agent.parse()` turns that into an `AgentRun`.
`Harness._execute()` wires these three calls together. `RunBuilder` wraps
`Harness` with a fluent API and handles workdir snapshotting and file diffing.

An agent only runs correctly inside the image built for it, and nothing in the
type system enforces that pairing — so it lives in exactly one place per agent:
`ClaudeCodeHarness.docker()`, `PiHarness.with_model()`.
Build harnesses through those, not by calling `Harness(agent, DockerExecutor(...))`
directly. `tea.executor` holds the executor-agnostic types only; `DockerProfile`
and `DockerExecutor` come from `tea.executor.docker_executor`.

### Judge

A separate call path invoked only when `check_output_score()` / `check_run_score()`
is used in a test:

```
check_output_score() / check_run_score()
└── Judge (ABC)          judge/judge.py
     └── PydanticAIJudge judge/pydantic_ai.py — calls an LLM via pydantic-ai, validates score with Pydantic
```

`Judge.evaluate(content, prompt)` returns a `JudgeResult(score, rationale)`.
`PydanticAIJudge` is the only file that imports pydantic-ai. Swapping provider
means implementing a new `Judge` adapter — no changes to callers.

### Adding a new provider or backend

- **New agent** (e.g. Codex, Gemini CLI): implement `Agent` ABC, add to `agent/__init__.py`
- **New executor** (e.g. subprocess, k8s): implement `Executor` ABC
- **New judge backend**: implement `Judge` ABC, wire it up via `default_judge()` or pass directly as `judge=` to the judge checkers

Callers (`Harness`, the judge checkers) depend only on the ABCs, never on concrete adapters.

## Environment variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | API key for the ClaudeCode agent running inside Docker (recommended) |
| `CLAUDE_CODE_OAUTH_TOKEN` | Long-term token (`claude setup-token`) for the ClaudeCode agent; supported alternative to `ANTHROPIC_API_KEY` |
| `CLAUDE_CODE_VERSION` | Pin the `@anthropic-ai/claude-code` version used inside Docker (auto-detected from `claude --version` / npm if unset) |
| `PI_VERSION` | Pin the `pi` version used inside Docker (auto-detected from `pi --version` / npm if unset) |
| `TEA_JUDGE_MODEL` | Judge model (default: `anthropic:claude-haiku-4-5-20251001`) |
| `TEA_JUDGE_BASE_URL` | When set, routes judge calls through an OpenAI-compatible endpoint (OpenRouter, Ollama, vLLM, etc.) |
| `TEA_JUDGE_API_KEY` | API key for the above; defaults to `"local"` when base_url is set |
