from __future__ import annotations

import json
import re

from tea.agent.claude_code import ClaudeCode
from tea.agent.harness import Harness
from tea.executor.docker import DockerExecutor

from .judge import Judge, JudgeResult

_JUDGE_PROMPT = """{prompt}

Content to evaluate:
{content}

Respond with ONLY a JSON object, no other text:
{{"score": <float 0.0–1.0>, "rationale": "<one sentence>"}}"""

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def _default_harness():
    return Harness(ClaudeCode(model=_DEFAULT_MODEL, max_turns=1), DockerExecutor())


class HarnessJudge(Judge):
    """Judge that runs evaluation through the ClaudeCode harness.

    Uses the same Docker + auth setup as the main agent so no additional
    credentials or dependencies are required.
    """

    def __init__(self, harness=None) -> None:
        if harness is None:
            harness = _default_harness()
        self._harness = harness

    def evaluate(self, content: str, prompt: str) -> JudgeResult:
        full_prompt = _JUDGE_PROMPT.format(prompt=prompt, content=content)
        run = self._harness.prompt(full_prompt).run()
        text = "\n".join(s.content for s in run.steps if s.type == "text")
        return _parse(text)


def _parse(text: str) -> JudgeResult:
    match = re.search(r"\{[^{}]*\"score\"\s*:[^{}]*\}", text, re.DOTALL)
    if not match:
        raise ValueError(
            f"Judge did not return a valid JSON score. Output: {text[:300]}"
        )
    data = json.loads(match.group())
    score = float(data["score"])
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"Judge score {score} out of range [0.0, 1.0]")
    return JudgeResult(score=score, rationale=str(data.get("rationale", "")))
