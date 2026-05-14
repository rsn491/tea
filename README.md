# harntest
Test and evaluation tool for agentic workflows. `harntest` helps benchmark how context and tools impact agent performance on your tasks.

![Demo output](docs/demo_output.png)

## Write a test

```python
from harntest import Agent, check_diff_added, check_skill_used

def test_add_minus_operation():
    run = (
        Agent.ClaudeCode
        .prompt("Add 'minus' operation support to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )

    check_skill_used(run, "add-new-operation")
    check_diff_added(run, "calculator.py", "minus")
    check_diff_added(run, "test_calculator.py", "test_minus")
    check_diff_added(run, "README.md", "minus")
```

See [examples/demo_calculator/agent-tests](examples/demo_calculator/agent-tests) for more examples.

## Run tests

Run all tests in a folder:

```bash
harntest examples/demo_calculator/agent-tests
```

Run one file with multiple iterations:

```bash
harntest examples/demo_calculator/agent-tests/test_add_new_operation.py -n 5
```

Run one test function:

```bash
harntest examples/demo_calculator/agent-tests/test_add_new_operation.py::test_add_minus_operation
```

## Requirements

- Python 3.11+
- Docker
- `CLAUDE_CODE_OAUTH_TOKEN` exported in your environment

## Install

```bash
pip install -e .
```


## Development

Install dev dependencies and enable git pre-commit hooks:

```bash
pip install -r requirements-dev.txt
pre-commit install
```

Run checks manually:

```bash
pre-commit run --all-files
pytest tests/unit -q
```
