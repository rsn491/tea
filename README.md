# harntest
Testing tool for agentic CLIs — runs agents in Docker and measures step count, token count, and assertion pass rates across multiple iterations.

## Requirements

- Docker
- `CLAUDE_CODE_OAUTH_TOKEN` (for Claude Code) or `OPENAI_API_KEY` (for Codex)

## Install

```bash
pip install -e .
```

## Writing a test

Use `check(label, condition)` for named assertions and `TestRunner` to run across multiple iterations:

```python
from harntest import Agent, TestRunner, check

def test_add_minus_operation():
    result = (
        Agent.ClaudeCode
            .prompt("Add 'minus' operation support to the calculator")
            .workdir("examples/demo_calculator")
            .run()
    )

    check("skills contains add-new-operation", "add-new-operation" in result.skills)
    check("calculator.py diff contains minus", "minus" in result.diff("calculator.py"))
    check("test_calculator.py diff contains test_minus", "test_minus" in result.diff("test_calculator.py"))
    check("README.md diff contains minus", "minus" in result.diff("README.md"))

if __name__ == "__main__":
    TestRunner(iterations=5).run(test_add_minus_operation)
```

## Running

```bash
python examples/test_add_new_operation.py
```

Example output:

```
  running: test_add_minus_operation  [5 iteration(s)]

     ✓ skills contains add-new-operation.......: 100.00%  ✓ 5  ✗ 0
     ✓ calculator.py diff contains minus.......: 100.00%  ✓ 5  ✗ 0
     ✓ test_calculator.py diff contains test_minus.: 80.00%  ✓ 4  ✗ 1
     ✓ README.md diff contains minus...........: 100.00%  ✓ 5  ✗ 0
       step_count................................: avg=12.4
       token_count...............................: avg=1240
       duration..................................: avg=45.2s
       iterations................................: 5
```

## API

### `check(label, condition)`

Named assertion. Inside a `TestRunner` it records pass/fail per label. Outside it raises `AssertionError` on failure, so it works in plain pytest tests too.

### `TestRunner(iterations=N).run(test_fn)`

Runs `test_fn` N times and prints aggregated metrics.

### `Agent.ClaudeCode` / `Agent.Codex`

Builder for launching an agent in Docker:

```python
result = (
    Agent.ClaudeCode
        .prompt("...")        # required
        .workdir("path/to")   # copy into container
        .maxTurns(25)         # default 25
        .run()
)
```

`run()` returns an `AgentRun` with:
- `result.skills` — list of Claude Code skill names used
- `result.diff("file.py")` — unified diff string for a changed file
- `result.step_count` — number of steps taken
- `result.token_count` — estimated token count
- `result.duration_s` — wall-clock seconds
