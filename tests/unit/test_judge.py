from __future__ import annotations

import pytest

from harntest.agent.agent_run import AgentRun, FileChange, FileDiff, Step
from harntest.checkers import check_judge_task
from harntest.judge import Judge, JudgeResult


class _StubJudge(Judge):
    def __init__(self, score: float, rationale: str = "stub") -> None:
        self._score = score
        self._rationale = rationale

    def evaluate(self, content: str, prompt: str) -> JudgeResult:
        return JudgeResult(score=self._score, rationale=self._rationale)


def _make_run(steps: list[Step] | None = None) -> AgentRun:
    return AgentRun(raw="", steps=steps or [], tools=[], skills=[])


# --- JudgeResult ---


def test_judge_result_fields():
    r = JudgeResult(score=0.9, rationale="looks good")
    assert r.score == 0.9
    assert r.rationale == "looks good"


# --- Judge seam ---


def test_stub_judge_satisfies_seam():
    judge = _StubJudge(score=0.7)
    result = judge.evaluate("some diff", "does this look right?")
    assert isinstance(result, JudgeResult)
    assert result.score == 0.7


# --- check_judge_task ---


def test_check_judge_task_passes_when_score_meets_threshold():
    run = _make_run()
    score = check_judge_task(
        run, diff="diff text", prompt="p", min_score=0.8, judge=_StubJudge(0.9)
    )
    assert score == 0.9


def test_check_judge_task_passes_at_exact_threshold():
    run = _make_run()
    score = check_judge_task(
        run, diff="diff text", prompt="p", min_score=0.5, judge=_StubJudge(0.5)
    )
    assert score == 0.5


def test_check_judge_task_raises_when_score_below_threshold():
    run = _make_run()
    with pytest.raises(AssertionError):
        check_judge_task(
            run, diff="diff text", prompt="p", min_score=0.8, judge=_StubJudge(0.4)
        )


def test_check_judge_task_returns_float():
    run = _make_run()
    result = check_judge_task(
        run, diff="x", prompt="p", min_score=0.0, judge=_StubJudge(0.6)
    )
    assert isinstance(result, float)


# --- AgentRun.transcript ---


def test_transcript_reconstructs_steps():
    steps = [
        Step(type="text", content="hello", raw={}),
        Step(type="tool_use", content='{"cmd": "ls"}', raw={}),
        Step(type="tool_result", content="file.py", raw={}),
    ]
    run = _make_run(steps)
    transcript = run.transcript
    assert "[assistant] hello" in transcript
    assert '[tool_use] {"cmd": "ls"}' in transcript
    assert "[tool_result] file.py" in transcript


def test_transcript_empty_when_no_steps():
    run = _make_run()
    assert run.transcript == ""


# --- AgentRun.diff ---


def test_diff_returns_unified_string():
    file_change = FileChange(
        path="calc.py",
        diff=FileDiff(
            added="x = 1", removed="", unified="--- calc.py\n+++ calc.py\n+x = 1"
        ),
    )
    run = _make_run()
    run._files_changed_fn = lambda: {"calc.py": file_change}
    assert run.diff("calc.py") == "--- calc.py\n+++ calc.py\n+x = 1"


def test_diff_returns_empty_string_for_unknown_file():
    run = _make_run()
    run._files_changed_fn = lambda: {}
    assert run.diff("nonexistent.py") == ""


# --- default_judge() env var wiring ---


def _clear_judge_env(monkeypatch):
    for var in (
        "HARNTEST_JUDGE_MODEL",
        "HARNTEST_JUDGE_BASE_URL",
        "HARNTEST_JUDGE_API_KEY",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)


def test_default_judge_raises_without_any_config(monkeypatch):
    _clear_judge_env(monkeypatch)

    from harntest.judge.pydantic_ai import default_judge

    with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
        default_judge()


def test_default_judge_falls_back_to_claude_judge_when_anthropic_key_set(monkeypatch):
    from unittest.mock import patch

    _clear_judge_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from harntest.judge import ClaudeJudge
    from harntest.judge.pydantic_ai import default_judge

    with patch("harntest.judge.claude.Agent"):
        judge = default_judge()

    assert isinstance(judge, ClaudeJudge)


def test_default_judge_falls_back_to_claude_judge_with_oauth_token(monkeypatch):
    from unittest.mock import MagicMock, patch

    _clear_judge_env(monkeypatch)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-test-token")

    from harntest.judge import ClaudeJudge
    from harntest.judge.pydantic_ai import default_judge

    mock_anthropic_client = MagicMock()

    with patch("anthropic.AsyncAnthropic", return_value=mock_anthropic_client):
        with patch("harntest.judge.claude.Agent"):
            judge = default_judge()

    assert isinstance(judge, ClaudeJudge)


def test_default_judge_raises_with_base_url_but_no_api_key(monkeypatch):
    monkeypatch.setenv("HARNTEST_JUDGE_MODEL", "llama3.2")
    monkeypatch.setenv("HARNTEST_JUDGE_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("HARNTEST_JUDGE_API_KEY", raising=False)

    from harntest.judge.pydantic_ai import default_judge

    with pytest.raises(EnvironmentError, match="HARNTEST_JUDGE_API_KEY"):
        default_judge()


def test_default_judge_raises_with_api_key_but_no_base_url(monkeypatch):
    monkeypatch.setenv("HARNTEST_JUDGE_MODEL", "llama3.2")
    monkeypatch.delenv("HARNTEST_JUDGE_BASE_URL", raising=False)
    monkeypatch.setenv("HARNTEST_JUDGE_API_KEY", "local")

    from harntest.judge.pydantic_ai import default_judge

    with pytest.raises(EnvironmentError, match="HARNTEST_JUDGE_BASE_URL"):
        default_judge()


def test_default_judge_reads_env_vars(monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("HARNTEST_JUDGE_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("HARNTEST_JUDGE_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("HARNTEST_JUDGE_API_KEY", "local")

    mock_model_cls = MagicMock()
    mock_provider_cls = MagicMock()

    # Patch at the source so the local imports inside _resolve_model pick them up.
    with (
        patch("pydantic_ai.models.openai.OpenAIChatModel", mock_model_cls),
        patch("pydantic_ai.providers.openai.OpenAIProvider", mock_provider_cls),
        patch("harntest.judge.pydantic_ai.Agent"),
    ):
        from harntest.judge.pydantic_ai import default_judge

        default_judge()

        mock_provider_cls.assert_called_once_with(
            base_url="http://localhost:11434/v1", api_key="local"
        )
        mock_model_cls.assert_called_once_with(
            "gpt-4o-mini", provider=mock_provider_cls.return_value
        )
