from __future__ import annotations

import importlib.util
import textwrap
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tea._context import _active_checks, _active_collector
from tea.agent.agent_run import AgentRun
from tea.runner import (
    TestCase,
    TestRunner,
    _discover_test_cases,
    collect_fns,
    discover_test_files,
    iterations,
    load_module,
)

# ── helpers ───────────────────────────────────────────────────────────────────

_DUMMY_RUN = AgentRun(raw="", steps=[], tools=[], skills=[])

# A no-op spinner that satisfies the context-manager and paused() protocol.
_NULL_SPINNER = MagicMock()
_NULL_SPINNER.__enter__ = lambda s, *_: s
_NULL_SPINNER.__exit__ = MagicMock(return_value=False)
_NULL_SPINNER.paused.return_value.__enter__ = lambda s, *_: s
_NULL_SPINNER.paused.return_value.__exit__ = MagicMock(return_value=False)


def _patch_tui():
    """Suppress all TUI output (spinner + report printers)."""
    return [
        patch("tea.runner._Spinner", return_value=_NULL_SPINNER),
        patch("tea.runner.print_test_header"),
        patch("tea.runner.print_test_results"),
    ]


# ── discover_test_files ───────────────────────────────────────────────────────


def test_discover_test_files_returns_single_file_when_given_a_file(tmp_path):
    f = tmp_path / "test_foo.py"
    f.touch()
    assert discover_test_files(f) == [f]


def test_discover_test_files_finds_test_py_files_in_directory(tmp_path):
    (tmp_path / "test_a.py").touch()
    (tmp_path / "test_b.py").touch()
    (tmp_path / "helper.py").touch()  # should be ignored
    result = discover_test_files(tmp_path)
    assert result == sorted([tmp_path / "test_a.py", tmp_path / "test_b.py"])


def test_discover_test_files_returns_sorted_results(tmp_path):
    (tmp_path / "test_z.py").touch()
    (tmp_path / "test_a.py").touch()
    result = discover_test_files(tmp_path)
    assert result == [tmp_path / "test_a.py", tmp_path / "test_z.py"]


# ── collect_fns ───────────────────────────────────────────────────────────────


def test_collect_fns_returns_test_prefixed_callables(tmp_path):
    mod_path = tmp_path / "sample.py"
    mod_path.write_text(
        textwrap.dedent("""\
        def test_alpha(): pass
        def test_beta(): pass
        def helper(): pass
        NOT_A_FN = 42
    """)
    )
    module = load_module(mod_path)
    fns = collect_fns(module)
    names = {f.__name__ for f in fns}
    assert names == {"test_alpha", "test_beta"}


def test_collect_fns_ignores_non_callables(tmp_path):
    mod_path = tmp_path / "sample.py"
    mod_path.write_text("test_value = 123\n")
    module = load_module(mod_path)
    assert collect_fns(module) == []


# ── iterations decorator ──────────────────────────────────────────────────────


def test_iterations_decorator_sets_attribute():
    @iterations(5)
    def test_foo():
        pass

    assert test_foo._tea_iterations == 5


def test_iterations_decorator_returns_original_callable():
    called = []

    @iterations(3)
    def test_bar():
        called.append(True)

    test_bar()
    assert called == [True]


# ── _discover_test_cases ──────────────────────────────────────────────────────


def test_discover_test_cases_with_double_colon_returns_single_case(tmp_path):
    mod = tmp_path / "test_thing.py"
    mod.write_text("def test_hello(): pass\n")
    cases = _discover_test_cases(f"{mod}::test_hello")
    assert len(cases) == 1
    assert isinstance(cases[0], TestCase)
    assert cases[0].path == mod
    assert cases[0].fn.__name__ == "test_hello"


def test_discover_test_cases_from_directory(tmp_path):
    (tmp_path / "test_a.py").write_text("def test_one(): pass\ndef test_two(): pass\n")
    (tmp_path / "test_b.py").write_text("def test_three(): pass\n")
    cases = _discover_test_cases(str(tmp_path))
    names = {tc.fn.__name__ for tc in cases}
    assert names == {"test_one", "test_two", "test_three"}
    assert all(isinstance(tc, TestCase) for tc in cases)


# ── TestRunner._run_one_iteration ─────────────────────────────────────────────


def test_run_one_iteration_calls_fn_once():
    calls = []
    TestRunner._run_one_iteration(lambda: calls.append(1), [])
    assert calls == [1]


def test_run_one_iteration_resets_context_vars_after_run():
    sentinel = object()
    c_token = _active_collector.set([sentinel])
    ch_token = _active_checks.set([])
    try:
        TestRunner._run_one_iteration(lambda: None, [])
        # After the iteration the context var must be restored to the outer value.
        assert _active_collector.get() == [sentinel]
    finally:
        _active_collector.reset(c_token)
        _active_checks.reset(ch_token)


def test_run_one_iteration_captures_exception_without_raising():
    errors: list[Exception] = []

    def _raise():
        raise ValueError("boom")

    TestRunner._run_one_iteration(_raise, errors)
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)


def test_run_one_iteration_returns_collector_and_checks():
    def _fn():
        _active_collector.get().append(_DUMMY_RUN)
        _active_checks.get().append(("my_check", True))

    collector, checks = TestRunner._run_one_iteration(_fn, [])
    assert collector == [_DUMMY_RUN]
    assert checks == [("my_check", True)]


# ── TestRunner.collect ────────────────────────────────────────────────────────


def test_collect_runs_fn_n_times():
    calls = []
    TestRunner().collect(lambda: calls.append(1), iterations=3)
    assert calls == [1, 1, 1]


def test_collect_result_has_correct_iteration_count():
    result = TestRunner().collect(lambda: None, iterations=4)
    assert result.iterations == 4


def test_collect_accumulates_check_results_across_iterations():
    i = 0

    def _fn():
        nonlocal i
        _active_checks.get().append(("label", i % 2 == 0))
        i += 1

    result = TestRunner().collect(_fn, iterations=3)
    assert result.check_results["label"] == [True, False, True]


def test_collect_accumulates_runs_across_iterations():
    def _fn():
        _active_collector.get().append(_DUMMY_RUN)

    result = TestRunner().collect(_fn, iterations=2)
    assert len(result.all_runs) == 2


def test_collect_records_errors_without_stopping():
    calls = []

    def _fn():
        calls.append(1)
        raise RuntimeError("fail")

    result = TestRunner().collect(_fn, iterations=3)
    assert calls == [1, 1, 1]
    assert len(result.run_errors) == 3


def test_collect_calls_on_iteration_callback():
    seen: list[tuple[int, int]] = []

    def _on_iter(i: int, n: int) -> None:
        seen.append((i, n))

    TestRunner().collect(lambda: None, on_iteration=_on_iter, iterations=3)
    assert seen == [(0, 3), (1, 3), (2, 3)]


# ── TestRunner.run_all — sequential (workers=1) ───────────────────────────────


def test_run_all_sequential_runs_every_test_case():
    calls = []
    cases = [
        TestCase(Path("test_x.py"), lambda: calls.append("a")),
        TestCase(Path("test_x.py"), lambda: calls.append("b")),
    ]
    patches = _patch_tui()
    for p in patches:
        p.start()
    try:
        TestRunner(workers=1).run_all(cases)
    finally:
        for p in patches:
            p.stop()
    assert sorted(calls) == ["a", "b"]


def test_run_all_sequential_respects_tea_iterations():
    calls = []

    def _fn():
        calls.append(1)

    _fn._tea_iterations = 3
    cases = [TestCase(Path("test_x.py"), _fn)]
    patches = _patch_tui()
    for p in patches:
        p.start()
    try:
        TestRunner(workers=1, iterations=1).run_all(cases)
    finally:
        for p in patches:
            p.stop()
    assert calls == [1, 1, 1]


# ── TestRunner.run_all — parallel (workers>1) ────────────────────────────────


def test_run_all_parallel_runs_every_test_case():
    calls = []
    lock = threading.Lock()

    def make_fn(name):
        def _fn():
            with lock:
                calls.append(name)

        _fn.__name__ = name
        return _fn

    cases = [
        TestCase(Path("test_x.py"), make_fn("a")),
        TestCase(Path("test_x.py"), make_fn("b")),
        TestCase(Path("test_x.py"), make_fn("c")),
    ]
    patches = _patch_tui()
    for p in patches:
        p.start()
    try:
        TestRunner(workers=3).run_all(cases)
    finally:
        for p in patches:
            p.stop()
    assert sorted(calls) == ["a", "b", "c"]


def test_run_all_parallel_respects_tea_iterations():
    calls = []
    lock = threading.Lock()

    def _fn():
        with lock:
            calls.append(1)

    _fn.__name__ = "test_fn"
    _fn._tea_iterations = 2
    cases = [TestCase(Path("test_x.py"), _fn)]
    patches = _patch_tui()
    for p in patches:
        p.start()
    try:
        TestRunner(workers=2, iterations=1).run_all(cases)
    finally:
        for p in patches:
            p.stop()
    assert calls == [1, 1]


# ── load_module (existing error-path tests kept here for completeness) ─────────


def test_load_module_raises_import_error_when_spec_is_none(tmp_path):
    non_py = tmp_path / "not_python.txt"
    non_py.write_text("hello")
    with pytest.raises(ImportError, match="recognisable Python file"):
        load_module(non_py)


def test_load_module_raises_import_error_when_loader_is_none(tmp_path):
    dummy = tmp_path / "dummy.py"
    dummy.write_text("x = 1")
    fake_spec = importlib.util.spec_from_file_location("dummy", dummy)
    assert fake_spec is not None
    fake_spec.loader = None  # type: ignore[assignment]
    with patch("importlib.util.spec_from_file_location", return_value=fake_spec):
        with pytest.raises(ImportError, match="recognisable Python file"):
            load_module(dummy)
