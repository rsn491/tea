from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tea.agent.agent_run import AgentRun, FileChange, FileDiff, Step
from tea.checkers import check_judge_task
from tea.judge import HarnessJudge, Judge, JudgeResult
from tea.judge.harness_judge import _parse
from tea.judge.pydantic_ai import default_judge, external_judge


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


def test_check_judge_task_raises_type_error_for_non_judge():
    run = _make_run()
    with pytest.raises(TypeError, match="Judge instance"):
        check_judge_task(run, diff="x", prompt="p", judge=object())


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


def test_default_judge_always_returns_harness_judge():
    assert isinstance(default_judge(), HarnessJudge)


def test_external_judge_raises_without_model_env_var(monkeypatch):
    monkeypatch.delenv("TEA_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("TEA_JUDGE_BASE_URL", raising=False)
    monkeypatch.delenv("TEA_JUDGE_API_KEY", raising=False)

    with pytest.raises(EnvironmentError, match="TEA_JUDGE_MODEL"):
        external_judge()


# --- HarnessJudge._parse ---


def test_harness_judge_parse_extracts_score_and_rationale():
    result = _parse('{"score": 0.85, "rationale": "looks good"}')
    assert result.score == 0.85
    assert result.rationale == "looks good"


def test_harness_judge_parse_tolerates_surrounding_text():
    result = _parse('Here is my answer:\n{"score": 0.5, "rationale": "ok"}\nDone.')
    assert result.score == 0.5


def test_harness_judge_parse_raises_when_no_json():
    with pytest.raises(ValueError, match="valid JSON score"):
        _parse("I think it looks good overall.")


def test_external_judge_raises_with_base_url_but_no_api_key(monkeypatch):
    monkeypatch.setenv("TEA_JUDGE_MODEL", "llama3.2")
    monkeypatch.setenv("TEA_JUDGE_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("TEA_JUDGE_API_KEY", raising=False)

    with pytest.raises(EnvironmentError, match="TEA_JUDGE_API_KEY"):
        external_judge()


def test_external_judge_raises_with_api_key_but_no_base_url(monkeypatch):
    monkeypatch.setenv("TEA_JUDGE_MODEL", "llama3.2")
    monkeypatch.delenv("TEA_JUDGE_BASE_URL", raising=False)
    monkeypatch.setenv("TEA_JUDGE_API_KEY", "local")

    with pytest.raises(EnvironmentError, match="TEA_JUDGE_BASE_URL"):
        external_judge()


def test_external_judge_reads_env_vars(monkeypatch):
    monkeypatch.setenv("TEA_JUDGE_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("TEA_JUDGE_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("TEA_JUDGE_API_KEY", "local")

    mock_model_cls = MagicMock()
    mock_provider_cls = MagicMock()

    with (
        patch("tea.judge.pydantic_ai.OpenAIChatModel", mock_model_cls),
        patch("tea.judge.pydantic_ai.OpenAIProvider", mock_provider_cls),
        patch("tea.judge.pydantic_ai.Agent"),
    ):
        external_judge()

        mock_provider_cls.assert_called_once_with(
            base_url="http://localhost:11434/v1", api_key="local"
        )
        mock_model_cls.assert_called_once_with(
            "gpt-4o-mini", provider=mock_provider_cls.return_value
        )
