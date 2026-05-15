# LLM-as-judge

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

## Configuring the judge

No extra configuration is needed. By default `check_judge_task` uses the same ClaudeCode harness (Docker + `claude-haiku`) that runs the main agent, so whatever auth you already have set up just works.

The tradeoff is an extra Docker call per judge invocation. To use a standalone external model instead, use `external_judge()` and set the env vars below. All three are required together:

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

Then pass it explicitly:

```python
from harntest import check_judge_task, external_judge

check_judge_task(run, diff=..., prompt=..., judge=external_judge())
```
