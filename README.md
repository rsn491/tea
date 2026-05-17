# tea - testing and evaluation for agents

Test and evaluation tool for agentic workflows. Run an agent against a task, assert what it did and measure how it performed.

![Demo output](docs/demo_output.png)

## Getting started

### Requirements

- Python 3.11+
- Docker
- A Claude Code OAuth token (`CLAUDE_CODE_OAUTH_TOKEN`)

### Install

```bash
pip install -e .
```

### Set up credentials

```bash
export CLAUDE_CODE_OAUTH_TOKEN="<your-token>"   # obtained via: claude auth login
```

### Write a test

```python
from tea import Agents, check_diff_added, check_skill_used

def test_add_minus_operation():
    run = (
        Agents.ClaudeCode
        .prompt("Add 'minus' operation support to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )

    check_skill_used(run, "add-new-operation")
    check_diff_added(run, "calculator.py", "minus")
    check_diff_added(run, "test_calculator.py", "test_minus")
```

### Run tests

```bash
# Run all tests in a folder
tea examples/demo_calculator/agent-tests

# Run one file, repeated 5 times to measure pass rate
tea examples/demo_calculator/agent-tests/test_add_new_operation.py -n 5

# Run a single test function
tea examples/demo_calculator/agent-tests/test_add_new_operation.py::test_add_minus_operation
```

See [examples/demo_calculator/agent-tests](examples/demo_calculator/agent-tests) for runnable examples.

## LLM-as-judge

Use `check_judge_task` to grade runs with a language model for assertions that are hard to express deterministically. See [docs/llm-as-judge.md](docs/llm-as-judge.md) for full usage and configuration.

## Assertions

Three built-in checkers for deterministic assertions:

```python
from tea import check, check_skill_used, check_diff_added

check("label", condition)                        # generic named assertion
check_skill_used(run, "skill-name")              # verify a skill was invoked
check_diff_added(run, "file.py", "some_symbol")  # verify code was added to a file
```

---

## Configuration

The agent that executes your task runs inside Docker. Configure it via:

| Variable | Purpose |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Auth token for the ClaudeCode agent |

---

## GitHub Actions

tea ships a reusable workflow you can call from any repo. It handles Python setup, Docker, and artifact upload — you bring the tests and credentials.

### Quickstart

Create `.github/workflows/agent-tests.yml` in your repo:

```yaml
on:
  push:
    branches: [main]
  pull_request:

jobs:
  agent-tests:
    uses: rsn491/tea/.github/workflows/harntest.yml@main
    with:
      test-path: examples/agent-tests
      iterations: 3
    secrets: inherit
```

`secrets: inherit` forwards your repo's secrets into the workflow automatically — no per-secret mapping needed.

### Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `test-path` | yes | — | Path to test directory or file |
| `iterations` | no | `1` | Times to run each test |

### Wiring credentials

Add secrets in your repo's **Settings → Secrets and variables → Actions**. Which secrets you need depends on your agent backend:

| Backend | Secret(s) to add |
|---|---|
| ClaudeCode (OAuth) | `CLAUDE_CODE_OAUTH_TOKEN` |
| ClaudeCode (API key) | `ANTHROPIC_API_KEY` |
| Codex | `OPENAI_API_KEY` |
| Pi + cloud provider | e.g. `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` |
| Pi + self-hosted (Ollama, vLLM) | `PI_API_KEY`, `PI_BASE_URL`, `PI_MODEL` |

Your test file reads whatever it needs from the environment:

```python
import os
from tea import Agents, check_diff_added
from tea.agent.pi import PiConfig

def test_add_feature():
    run = (
        Agents.Pi
        .with_model(PiConfig(
            model=os.environ["PI_MODEL"],
            api_key_env="PI_API_KEY",
            base_url=os.environ.get("PI_BASE_URL"),
        ))
        .prompt("Add 'minus' operation to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )
    check_diff_added(run, "calculator.py", "minus")
```

The workflow uploads the full tea output as a `tea-test-output` artifact on every run, including failures.

---

## Development

```bash
pip install -e ".[dev]"
pre-commit install
```

Run checks manually:

```bash
pre-commit run --all-files
pytest tests/unit -q
```
