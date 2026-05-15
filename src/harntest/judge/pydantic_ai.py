from __future__ import annotations

import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from .judge import Judge, JudgeResult


class _Score(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    rationale: str


class PydanticAIJudge(Judge):
    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        resolved: Model | str = _resolve_model(
            model, base_url=base_url, api_key=api_key
        )
        self._agent: Agent[None, _Score] = Agent(resolved, output_type=_Score)

    def evaluate(self, content: str, prompt: str) -> JudgeResult:
        message = f"{prompt}\n\nContent:\n{content}"
        result = self._agent.run_sync(message)
        return JudgeResult(score=result.output.score, rationale=result.output.rationale)


def default_judge() -> Judge:
    model = os.environ.get("HARNTEST_JUDGE_MODEL")
    base_url = os.environ.get("HARNTEST_JUDGE_BASE_URL")
    api_key = os.environ.get("HARNTEST_JUDGE_API_KEY")

    if not model and not base_url and not api_key:
        from .harness_judge import HarnessJudge

        return HarnessJudge()

    _validate_env(model=model, base_url=base_url, api_key=api_key)
    return PydanticAIJudge(model, base_url=base_url, api_key=api_key)  # type: ignore[arg-type]


def _validate_env(
    *, model: str | None, base_url: str | None, api_key: str | None
) -> None:
    if not model:
        raise EnvironmentError(
            "HARNTEST_JUDGE_MODEL is not set. "
            "Set it to a model string such as 'anthropic:claude-haiku-4-5-20251001' "
            "or 'openai:gpt-4o-mini'. See README for full configuration options."
        )
    if base_url and not api_key:
        raise EnvironmentError(
            "HARNTEST_JUDGE_BASE_URL is set but HARNTEST_JUDGE_API_KEY is not. "
            "Set HARNTEST_JUDGE_API_KEY to your API key, or 'local' for "
            "unauthenticated endpoints."
        )
    if api_key and not base_url:
        raise EnvironmentError(
            "HARNTEST_JUDGE_API_KEY is set but HARNTEST_JUDGE_BASE_URL is not. "
            "Set HARNTEST_JUDGE_BASE_URL to your endpoint URL."
        )


def _resolve_model(
    model: str, *, base_url: str | None, api_key: str | None
) -> Model | str:
    # When base_url is set, use an OpenAI-compatible client so any local server
    # (Ollama, vLLM, LM Studio) works regardless of the provider prefix in `model`.
    if base_url:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            model,
            provider=OpenAIProvider(base_url=base_url, api_key=api_key),
        )
    return model
