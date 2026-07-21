from __future__ import annotations

from tea.agent.agent_run import AgentRun, Step, StepType
from tea.baseline import SCHEMA_VERSION, Baseline, Metric, TestSummary
from tea.runner import _CollectResult

# ── helpers ───────────────────────────────────────────────────────────────────


def _run(step_words: int, duration_s: float) -> AgentRun:
    """An AgentRun with a controllable token_count / duration (one step each).

    token_count = round(#words * 0.75).
    """
    step = Step(type=StepType.TEXT, content="word " * step_words, raw={})
    return AgentRun(raw="", steps=[step], tools=[], skills=[], duration_s=duration_s)


def _result(runs: list[AgentRun], iterations: int, failed: int = 0) -> _CollectResult:
    return _CollectResult(
        all_runs=runs, iterations=iterations, failed_iterations=failed
    )


def _baseline(token_avg: float, success_rate: float = 1.0) -> Baseline:
    return Baseline(
        {
            "t": TestSummary(
                success_rate=success_rate,
                metrics={Metric.TOKEN_COUNT.key: {"avg": token_avg}},
            )
        }
    )


# ── TestSummary.from_result ───────────────────────────────────────────────────


def test_from_result_computes_success_rate():
    summary = TestSummary.from_result(_result([], iterations=4, failed=1))
    assert summary.success_rate == 0.75


def test_from_result_success_rate_is_zero_when_no_iterations():
    summary = TestSummary.from_result(_result([], iterations=0))
    assert summary.success_rate == 0.0


def test_from_result_metrics_empty_when_no_runs():
    summary = TestSummary.from_result(_result([], iterations=3))
    assert summary.metrics == {}


def test_from_result_averages_metrics_across_runs():
    runs = [_run(step_words=4, duration_s=2.0), _run(step_words=8, duration_s=4.0)]
    metrics = TestSummary.from_result(_result(runs, iterations=2)).metrics
    assert metrics["step_count"]["avg"] == 1.0
    # token_count = round(words * 0.75): run A=3, run B=6 → avg 4.5
    assert metrics["token_count"]["avg"] == 4.5
    assert metrics["duration"]["avg"] == 3.0


# ── Baseline serialization ────────────────────────────────────────────────────


def test_baseline_to_dict_includes_schema_version():
    data = Baseline({"t": TestSummary(success_rate=1.0)}).to_dict()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["tests"]["t"]["success_rate"] == 1.0


def test_baseline_write_and_load_round_trip(tmp_path):
    original = _baseline(3421)
    path = tmp_path / "nested" / "baseline.json"
    original.write(path)
    assert path.exists()
    assert Baseline.load(path).to_dict() == original.to_dict()


# ── Baseline.compare ──────────────────────────────────────────────────────────


def test_compare_flags_metric_rise_above_tolerance():
    regressions = _baseline(4600).compare(_baseline(3421), tol=0.10)
    assert len(regressions) == 1
    r = regressions[0]
    assert r.test == "t"
    assert r.metric is Metric.TOKEN_COUNT
    assert r.baseline_value == 3421
    assert r.current_value == 4600


def test_compare_ignores_metric_rise_within_tolerance():
    assert _baseline(3500).compare(_baseline(3421), tol=0.10) == []


def test_compare_flags_success_rate_drop():
    current = _baseline(3421, success_rate=0.6)
    previous = _baseline(3421, success_rate=1.0)
    regressions = current.compare(previous, tol=0.10)
    assert [r.metric for r in regressions] == [Metric.SUCCESS_RATE]
    assert regressions[0].baseline_value == 1.0
    assert regressions[0].current_value == 0.6


def test_compare_ignores_success_rate_drop_within_tolerance():
    current = _baseline(3421, success_rate=0.95)
    previous = _baseline(3421, success_rate=1.0)
    assert current.compare(previous, tol=0.10) == []


def test_compare_skips_tests_absent_from_current():
    assert Baseline().compare(_baseline(3421)) == []


def test_compare_skips_metric_when_baseline_value_is_zero():
    assert _baseline(100).compare(_baseline(0)) == []
