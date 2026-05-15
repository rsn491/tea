"""
Example: LLM-as-judge assertion using check_judge_task.

Configure your judge model via env vars before running:

    export HARNTEST_JUDGE_MODEL="llama3.2"
    export HARNTEST_JUDGE_BASE_URL="https://<your-ollama-cloud-host>/v1"
    export HARNTEST_JUDGE_API_KEY="<your-token>"

Then run:

    harntest examples/demo_calculator/agent-tests/test_judge_quality.py
"""

from harntest import Agents, check_judge_task


def test_minus_implementation_quality():
    run = (
        Agents.ClaudeCode.prompt("Add a 'minus' operation to the calculator")
        .workdir("examples/demo_calculator")
        .run()
    )

    check_judge_task(
        run,
        diff=run.diff("calculator.py"),
        prompt=(
            "Does this diff correctly implement a subtraction operation "
            "without breaking the existing structure? "
            "Score 1.0 if the implementation is clean and complete, "
            "0.5 if it works but has style issues, "
            "0.0 if it is broken or missing."
        ),
        min_score=0.7,
    )

    check_judge_task(
        run,
        diff=run.transcript,
        prompt=(
            "Did the agent make changes directly and confidently without "
            "unnecessary clarifying questions or excessive commentary? "
            "Score 1.0 for decisive execution, 0.0 for excessive hedging."
        ),
        min_score=0.6,
    )
