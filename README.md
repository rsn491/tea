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
from tea import (
    Agents,
    check_diff_added,
    check_file_changed,
    check_run_score,
    check_skill_used,
    iterations,
)


@iterations(3, max_failures=1)
def test_add_minus_operation():
    run = (
        Agents.ClaudeCode.prompt("Add 'minus' operation support to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )

    check_diff_added(run, "calculator.py", "def minus")
    check_file_changed(run, "README.md")
    check_skill_used(run, "add-new-operation")
    check_run_score(
        run,
        (
            "Does this diff correctly implement a subtraction operation "
            "without breaking the existing structure? "
            "Score 1.0 if the implementation is clean and complete, "
            "0.5 if it works but has style issues, "
            "0.0 if it is broken or missing."
        ),
        min_score=0.7,
    )
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

#### Metrics baselines

Export per-test metrics (average token count, step count, duration, and success
rate) to JSON, then compare later runs against it to catch regressions.
`--baseline` is warn-only — it flags any metric that worsened by more than 10%
but never changes the exit code.

```bash
tea examples/demo_calculator/agent-tests -n 3 --summary-export baseline.json
tea examples/demo_calculator/agent-tests -n 3 --baseline baseline.json
```

## Checkers

Checkers are the assertions of a tea test: each one inspects an agent run,
records a pass or a fail, and returns its result so you can build on it.

| Checker | Checks that | Returns |
|---|---|---|
| `check(label, condition)` | `condition` is truthy | `bool` |
| `check_skill_used(run, skill)` | the agent used `skill` | `bool` |
| `check_skill_not_used(run, skill)` | the agent did not use `skill` | `bool` |
| `check_tool_used(run, tool)` | the agent called `tool` | `bool` |
| `check_tool_not_used(run, tool)` | the agent did not call `tool` | `bool` |
| `check_file_changed(run, file)` | `file` was created or modified | `bool` |
| `check_file_not_changed(run, file)` | `file` was left untouched | `bool` |
| `check_diff_added(run, file, code)` | `code` appears in `file`'s added lines | `bool` |
| `check_diff_removed(run, file, code)` | `code` appears in `file`'s removed lines | `bool` |
| `check_output_score(output_to_evaluate, judge_prompt, min_score=0.5, judge=None)` | the score assigned to the output using an LLM-as-a-Judge is higher than `min_score` | the score, as `float` |
| `check_run_score(run, judge_prompt, min_score=0.5, judge=None)` | the score assigned to the agent run using an LLM-as-a-Judge is higher than `min_score` | the score, as `float` |

## Agents

### ClaudeCode

```python
Agents.ClaudeCode
    .prompt("Add 'minus' operation support to the calculator")
    .workdir("examples/demo_calculator")
    .run()
```

Setup `ANTHROPIC_API_KEY` (API-key auth, recommended). A long-term token
(`CLAUDE_CODE_OAUTH_TOKEN`, generated with `claude setup-token`) is also
supported.

To pick a model, pass its identifier to `with_model()`; the default is
`claude-haiku-4-5-20251001`:

```python
Agents.ClaudeCode.with_model("claude-opus-4-7").prompt("...").run()
```

### Pi

Pi requires a `PiConfig`:

```python
from tea.agent import PiConfig

Agents.Pi.with_model(PiConfig(
    model="ollama/qwen2.5-coder:1.5b",  # required
    api_key_env="MY_API_KEY",           # host env var forwarded into container
    base_url="http://host.docker.internal:11434/v1",  # OpenAI-compatible endpoint
))
```

| Field | Required | Purpose |
|---|---|---|
| `model` | Yes | Model identifier |
| `api_key_env` | No | Name of a host env var to forward into the container as the API key |
| `base_url` | No | OpenAI-compatible endpoint for custom or local providers |

`base_url` is used verbatim inside the container, so a provider running on
your machine must be addressed as `http://host.docker.internal:<port>` — not
`localhost`, which resolves to the container itself. Setting `base_url` makes
tea declare `host_network_access`, which is what makes that name resolve; the
address is still yours to write.

---

## Skills

Tea discovers project skills automatically from conventional, in-workdir paths
and copies them into the agent's native skill directory in the container.

| Agent | Default sources (searched in order) |
|---|---|
| ClaudeCode | `.claude/skills`, `.agents/skills` |
| Pi | `.pi/skills`, `.agents/skills` |

`.agents/skills` is the cross-agent convention — put a skill there and every
agent picks it up. Missing default paths are silently skipped. If the same
skill name appears in multiple sources, the earlier (agent-specific) source
wins.

Override the defaults with `skills_sources`:

```python
# One or more custom source paths (relative to the run's workdir).
Agents(skills_sources=["eval-fixtures/skills"])

# Per-run override.
Agents.ClaudeCode.prompt("...").workdir(".").skills_from(["custom/skills"]).run()

# Explicit opt-out: load no skills at all.
Agents(skills_sources=[])
```

Each skill is a directory containing a `SKILL.md` file with frontmatter:

```markdown
---
name: add-new-operation
description: How to add a new arithmetic operation to the calculator.
---

Step-by-step instructions live in the body of the file.
```

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
