from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tea.agent.agent_run import AgentRun, FileChange, FileDiff, Step, StepType
from tea.checkers import check_output_score, check_run_score
from tea.judge import HarnessJudge, Judge, JudgeResult
from tea.judge.harness_judge import _parse, default_judge
from tea.judge.pydantic_ai import external_judge


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


# --- check_output_score ---


def test_check_output_score_passes_when_score_meets_threshold():
    score = check_output_score("diff text", "p", min_score=0.8, judge=_StubJudge(0.9))
    assert score == 0.9


def test_check_output_score_passes_at_exact_threshold():
    score = check_output_score("diff text", "p", min_score=0.5, judge=_StubJudge(0.5))
    assert score == 0.5


def test_check_output_score_raises_when_score_below_threshold():
    with pytest.raises(AssertionError):
        check_output_score("diff text", "p", min_score=0.8, judge=_StubJudge(0.4))


def test_check_output_score_returns_float():
    result = check_output_score("x", "p", min_score=0.0, judge=_StubJudge(0.6))
    assert isinstance(result, float)


def test_check_output_score_evaluates_given_diff():
    judge = _StubJudge(0.9)
    judge.evaluate = MagicMock(wraps=judge.evaluate)

    check_output_score("EXPLICIT-DIFF", "p", min_score=0.0, judge=judge)

    assert judge.evaluate.call_args.args[0] == "EXPLICIT-DIFF"


# --- check_run_score ---


def test_check_run_score_evaluates_full_run_diff():
    run = _make_run()
    run._files_changed_fn = lambda: {
        "a.py": FileChange("a.py", FileDiff(added="", removed="", unified="DIFF-A")),
        "b.py": FileChange("b.py", FileDiff(added="", removed="", unified="DIFF-B")),
    }
    judge = _StubJudge(0.9)
    judge.evaluate = MagicMock(wraps=judge.evaluate)

    check_run_score(run, "p", min_score=0.0, judge=judge)

    judged_content = judge.evaluate.call_args.args[0]
    assert "DIFF-A" in judged_content
    assert "DIFF-B" in judged_content


# --- AgentRun.transcript ---


def test_transcript_reconstructs_steps():
    steps = [
        Step(type=StepType.TEXT, content="hello", raw={}),
        Step(type=StepType.TOOL_USE, content='{"cmd": "ls"}', raw={}),
        Step(type=StepType.TOOL_RESULT, content="file.py", raw={}),
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


# --- AgentRun.full_diff ---


def test_full_diff_concatenates_every_changed_file():
    run = _make_run()
    run._files_changed_fn = lambda: {
        "a.py": FileChange("a.py", FileDiff(added="", removed="", unified="DIFF-A")),
        "b.py": FileChange("b.py", FileDiff(added="", removed="", unified="DIFF-B")),
    }
    assert run.full_diff == "DIFF-A\nDIFF-B"


def test_full_diff_empty_when_no_files_changed():
    run = _make_run()
    run._files_changed_fn = lambda: {}
    assert run.full_diff == ""


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


def test_harness_judge_parse_raises_value_error_on_malformed_json():
    # A trailing comma is not valid JSON; the regex will match but json.loads must fail.
    # The fix wraps JSONDecodeError in a ValueError with context about the matched text.
    with pytest.raises(ValueError, match="malformed JSON"):
        _parse('{"score": 0.5, "rationale": "ok",}')


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
