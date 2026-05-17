# tea - testing and evaluation for agents

Test and evaluation tool for agentic workflows. Run an agent against a task, assert what it did and measure how it performed.

![Demo output](docs/demo_output.png)

## Getting started

### Requirements

- Python 3.11+
- Docker

### Install

```bash
pip install -e .
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
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

## Assertions

```python
from tea import check, check_skill_used, check_diff_added, check_judge_task

check("label", condition)                        # generic named assertion
check_skill_used(run, "skill-name")              # verify a skill was invoked
check_diff_added(run, "file.py", "some_symbol")  # verify code was added to a file
check_judge_task(run, diff=run.diff("file.py"), prompt="scoring criteria")  # LLM-as-judge assertion
```

## Agents

### ClaudeCode

```python
Agents.ClaudeCode
    .prompt("Add 'minus' operation support to the calculator")
    .workdir("examples/demo_calculator")
    .run()
```

Setup `CLAUDE_CODE_OAUTH_TOKEN` (OAuth token, subscription auth) or `ANTHROPIC_API_KEY` (API key auth).

### Codex

```python
Agents.Codex
    .prompt("Add 'minus' operation support to the calculator")
    .workdir("examples/demo_calculator")
    .run()
```

Setup `OPENAI_API_KEY` (OpenAI API key).

### Pi

Pi requires a `ModelConfig`:

```python
from tea.agent import ModelConfig

Agents.Pi.with_model(ModelConfig(
    model="ollama/qwen2.5-coder:1.5b",  # required
    api_key_env="MY_API_KEY",           # host env var forwarded into container
    base_url="http://localhost:11434",  # OpenAI-compatible endpoint
))
```

| Field | Required | Purpose |
|---|---|---|
| `model` | Yes | Model identifier |
| `api_key_env` | No | Name of a host env var to forward into the container as the API key |
| `base_url` | No | OpenAI-compatible endpoint for custom or local providers |

---

## Development

```bash
uv sync --group dev
uv run pre-commit install
```

Run checks manually:

```bash
uv run pre-commit run --all-files
uv run pytest tests/unit -q
```
