from __future__ import annotations

from pydantic_ai import Agent

from .judge import Judge, JudgeResult
from .pydantic_ai import _Score

_DEFAULT_JUDGE_MODEL = "claude-haiku-4-5-20251001"


class ClaudeJudge(Judge):
    """Judge backed by the Anthropic API.

    Supports both API key auth (ANTHROPIC_API_KEY) and OAuth subscription auth
    (CLAUDE_CODE_OAUTH_TOKEN), so it can reuse whichever credentials the main
    ClaudeCode agent is already using.
    """

    def __init__(
        self, model: str = _DEFAULT_JUDGE_MODEL, *, auth_token: str | None = None
    ) -> None:
        if auth_token:
            import anthropic
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            client = anthropic.AsyncAnthropic(auth_token=auth_token)
            resolved = AnthropicModel(
                model, provider=AnthropicProvider(anthropic_client=client)
            )
        else:
            resolved = f"anthropic:{model}"

        self._agent: Agent[None, _Score] = Agent(resolved, output_type=_Score)

    def evaluate(self, content: str, prompt: str) -> JudgeResult:
        message = f"{prompt}\n\nContent:\n{content}"
        result = self._agent.run_sync(message)
        return JudgeResult(score=result.output.score, rationale=result.output.rationale)
