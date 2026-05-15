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

Use `check_judge_task` to grade runs with a language model for assertions that are hard to express deterministically. See [docs/llm-as-judge.md](docs/llm-as-judge.md) for full usage and configuration.

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
