# LLM-as-judge

For assertions that are hard to express deterministically, use the judge
checkers to grade the run with a language model:

```python
from tea import check_judge_diff, check_judge_run

# Judge the whole-run diff (every file the agent changed)
check_judge_run(
    run,
    "Does this diff correctly implement minus without breaking existing tests? Score 0-1.",
    min_score=0.8,
)

# Narrow it to a single file's diff
check_judge_diff(
    run,
    "Does calculator.py correctly implement minus? Score 0-1.",
    run.diff("calculator.py"),
    min_score=0.8,
)

# Judge the full agent transcript
check_judge_diff(
    run,
    "Did the agent act decisively without asking unnecessary clarifying questions? Score 0-1.",
    run.transcript,
    min_score=0.6,
)
```

`check_judge_run` grades `run.full_diff` — the unified diff of every file the
agent changed. `check_judge_diff` grades whatever you pass as
`diff_to_evaluate`, such as a single file's diff or the transcript.

Both return the score as a float and raise `AssertionError` if it falls below `min_score`. The score and rationale appear in the test report.

The judge is **separate from the harness** — the agent that runs your task (ClaudeCode inside Docker) and the model that grades the result are independently configured. You can use a cheap local model as judge while running an expensive agent, or swap the judge without touching your agent setup.

## Configuring the judge

No extra configuration is needed. By default the judge checkers use the same ClaudeCode harness (Docker + `claude-haiku`) that runs the main agent, so whatever auth you already have set up just works.

The tradeoff is an extra Docker call per judge invocation. To use a standalone external model instead, use `external_judge()` and set the env vars below. All three are required together:

| Variable | Purpose |
|---|---|
| `TEA_JUDGE_MODEL` | Model name, including provider prefix |
| `TEA_JUDGE_BASE_URL` | Base URL for any OpenAI-compatible endpoint (OpenRouter, Ollama, vLLM, etc.) |
| `TEA_JUDGE_API_KEY` | API key for the above |

When `TEA_JUDGE_BASE_URL` is unset, the model string routes through the native provider SDK (e.g. `anthropic:...` uses the Anthropic API, picking up `ANTHROPIC_API_KEY` from the environment). When set, all calls go through the OpenAI-compatible path.

```bash
# Anthropic directly
export TEA_JUDGE_MODEL="anthropic:claude-haiku-4-5-20251001"

# OpenRouter
export TEA_JUDGE_BASE_URL="https://openrouter.ai/api/v1"
export TEA_JUDGE_API_KEY="sk-or-..."
export TEA_JUDGE_MODEL="google/gemma-3-27b-it"

# Local Ollama
export TEA_JUDGE_BASE_URL="http://localhost:11434/v1"
export TEA_JUDGE_API_KEY="local"
export TEA_JUDGE_MODEL="llama3.2"
```

Then pass it explicitly:

```python
from tea import check_judge_run, external_judge

check_judge_run(run, "scoring criteria", judge=external_judge())
```
