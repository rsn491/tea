from __future__ import annotations

from .pydantic_ai import PydanticAIJudge

_DEFAULT_JUDGE_MODEL = "anthropic:claude-haiku-4-5-20251001"


class ClaudeJudge(PydanticAIJudge):
    """Judge backed by the Anthropic API via ANTHROPIC_API_KEY.

    Used as the zero-config default when no HARNTEST_JUDGE_* vars are set,
    so any test run that already has an API key can use check_judge_task without
    extra setup.
    """

    def __init__(self, model: str = _DEFAULT_JUDGE_MODEL) -> None:
        super().__init__(model)
