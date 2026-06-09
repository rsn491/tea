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

Every `check_*` helper takes the `run` as its first argument, accepts an
optional `description` to override the generated label, and—inside a
`TestRunner`—records pass/fail without halting the test (outside one it raises
`AssertionError`).

```python
from tea import (
    check,
    check_skill_used,
    check_skill_not_used,
    check_tool_used,
    check_tool_not_used,
    check_file_changed,
    check_file_not_changed,
    check_diff_added,
    check_diff_removed,
    check_judge_task,
)

check("label", condition)                          # generic named assertion
check_skill_used(run, "skill-name")                # a skill was invoked
check_skill_not_used(run, "skill-name")            # a skill was NOT invoked
check_tool_used(run, "Edit")                        # a tool was called
check_tool_not_used(run, "Bash")                    # a tool was NOT called
check_file_changed(run, "file.py")                  # a file was created or modified
check_file_not_changed(run, "file.py")              # a file was left untouched
check_diff_added(run, "file.py", "some_symbol")    # code was added to a file
check_diff_removed(run, "file.py", "old_symbol")   # code was removed from a file
check_judge_task(run, diff=run.diff("file.py"), prompt="scoring criteria")  # LLM-as-judge assertion
```

| Checker | Asserts that… | Returns |
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
| `check_judge_task(run, *, diff, prompt, min_score=0.5, judge=None)` | an LLM judge scores `diff` ≥ `min_score` | `float` (score) |

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

Setup `OPENAI_API_KEY` (API-key auth). For ChatGPT subscription (OAuth) auth,
use `Agents.Codex.with_subscription()` and set `CODEX_AUTH_JSON` to the contents
of your `~/.codex/auth.json` (e.g. `export CODEX_AUTH_JSON="$(cat ~/.codex/auth.json)"`);
it is written into the container at start-up, no host file is mounted. Note the
default model differs by auth mode (`gpt-5.2-codex` for API key, a
subscription-compatible model for OAuth), since API-key models are rejected
under ChatGPT-account auth.

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

## Skills

Tea discovers project skills automatically from conventional, in-workdir paths
and copies them into the agent's native skill directory in the container.

| Agent | Default sources (searched in order) |
|---|---|
| ClaudeCode | `.claude/skills`, `.agents/skills` |
| Codex | `.codex/skills`, `.agents/skills` |
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
