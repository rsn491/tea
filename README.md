# harntest

Test and evaluation framework for agentic workflows. Run an agent against a task, assert on what it did, and measure pass rates across multiple iterations.

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
from harntest import Agents, check_diff_added, check_skill_used

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
harntest examples/demo_calculator/agent-tests

# Run one file, repeated 5 times to measure pass rate
harntest examples/demo_calculator/agent-tests/test_add_new_operation.py -n 5

# Run a single test function
harntest examples/demo_calculator/agent-tests/test_add_new_operation.py::test_add_minus_operation
```

See [examples/demo_calculator/agent-tests](examples/demo_calculator/agent-tests) for runnable examples.

## LLM-as-judge

For assertions that are hard to express deterministically, use `check_judge_task` to grade the run with a language model:

```python
from harntest import check_judge_task

# Judge a file diff
check_judge_task(
    run,
    diff=run.diff("calculator.py"),
    prompt="Does this diff correctly implement minus without breaking existing tests? Score 0-1.",
    min_score=0.8,
)

# Judge the full agent transcript
check_judge_task(
    run,
    diff=run.transcript,
    prompt="Did the agent act decisively without asking unnecessary clarifying questions? Score 0-1.",
    min_score=0.6,
)
```

`check_judge_task` returns the score as a float and raises `AssertionError` if it falls below `min_score`. The score and rationale appear in the test report.

The judge is **separate from the harness** — the agent that runs your task (ClaudeCode inside Docker) and the model that grades the result are independently configured. You can use a cheap local model as judge while running an expensive agent, or swap the judge without touching your agent setup.

### Configuring the judge

All three env vars are required when using `check_judge_task`:

| Variable | Purpose |
|---|---|
| `HARNTEST_JUDGE_MODEL` | Model name, including provider prefix |
| `HARNTEST_JUDGE_BASE_URL` | Base URL for any OpenAI-compatible endpoint (OpenRouter, Ollama, vLLM, etc.) |
| `HARNTEST_JUDGE_API_KEY` | API key for the above |

When `HARNTEST_JUDGE_BASE_URL` is unset, the model string routes through the native provider SDK (e.g. `anthropic:...` uses the Anthropic API, picking up `ANTHROPIC_API_KEY` from the environment). When set, all calls go through the OpenAI-compatible path.

```bash
# Anthropic directly
export HARNTEST_JUDGE_MODEL="anthropic:claude-haiku-4-5-20251001"

# OpenRouter
export HARNTEST_JUDGE_BASE_URL="https://openrouter.ai/api/v1"
export HARNTEST_JUDGE_API_KEY="sk-or-..."
export HARNTEST_JUDGE_MODEL="google/gemma-3-27b-it"

# Local Ollama
export HARNTEST_JUDGE_BASE_URL="http://localhost:11434/v1"
export HARNTEST_JUDGE_API_KEY="local"
export HARNTEST_JUDGE_MODEL="llama3.2"
```

## Requirements

---

## Assertions

Three built-in checkers for deterministic assertions:

```python
from harntest import check, check_skill_used, check_diff_added

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
