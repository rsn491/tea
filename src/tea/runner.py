from __future__ import annotations

import importlib.util
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

from tea._context import _active_checks, _active_collector
from tea.agent.agent_run import AgentRun
from tea.baseline import Baseline, TestSummary
from tea.collect_result import _CollectResult
from tea.infra.docker import Docker
from tea.tui import _bold_cyan, _cyan, _dim, _Spinner
from tea.tui.baseline_view import BaselineComparisonView
from tea.tui.runner_view import print_test_header, print_test_results


@dataclass
class TestCase:
    path: Path
    fn: Callable

    @property
    def id(self) -> str:
        """File-qualified identity, unique even when names repeat across files."""
        name = getattr(self.fn, "__name__", repr(self.fn))
        return f"{self.path}::{name}"


def discover_test_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("test_*.py"))


def load_module(path: Path) -> ModuleType:
    parent = str(path.parent.resolve())
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec = importlib.util.spec_from_file_location(path.stem, path.resolve())
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Cannot load module from '{path}': not a recognisable Python file"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_fns(module: ModuleType) -> list[Callable]:
    return [
        obj
        for name, obj in vars(module).items()
        if name.startswith("test_") and callable(obj)
    ]


def _discover_test_cases(target: str) -> list[TestCase]:
    if "::" in target:
        file_part, fn_name = target.split("::", 1)
        path = Path(file_part)
        module = load_module(path)
        fn = getattr(module, fn_name, None)
        if fn is None:
            print(f"tea: '{fn_name}' not found in {file_part}")
            sys.exit(1)
        return [TestCase(path, fn)]

    path = Path(target)
    return [
        TestCase(f, fn)
        for f in discover_test_files(path)
        for fn in collect_fns(load_module(f))
    ]


def run(
    target: str,
    default_iterations: int = 1,
    workers: int = 1,
    summary_export: str | None = None,
    baseline: str | None = None,
) -> bool:
    test_cases = _discover_test_cases(target)
    if not test_cases:
        print(f"tea: no tests found in '{target}'")
        sys.exit(1)
    runner = TestRunner(iterations=default_iterations, workers=workers)

    # Load any existing baseline before running so that exporting and comparing
    # to the same path in one invocation compares against the previous run
    # rather than the one we are about to write. Reading is warn-only: a missing
    # or malformed baseline must not fail an otherwise-passing run.
    previous = None
    if baseline:
        try:
            previous = Baseline.load(Path(baseline))
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"tea: cannot read baseline '{baseline}': {e}")

    ok = runner.run_all(test_cases)

    current = Baseline(runner.summaries)
    if summary_export:
        current.write(Path(summary_export))
    if previous is not None:
        BaselineComparisonView(current.compare(previous)).render()

    return ok


def iterations(n: int, max_failures: int = 0) -> Callable:
    """Decorator to set the iteration count and failure tolerance for a test.

    The test fails only if more than `max_failures` iterations fail.
    """
    if not 0 <= max_failures < n:
        raise ValueError(
            "max_failures must satisfy 0 <= max_failures < n "
            f"(got n={n}, max_failures={max_failures})"
        )

    def decorator(fn: Callable) -> Callable:
        fn._tea_iterations = n
        fn._tea_max_failures = max_failures
        return fn

    return decorator


class TestRunner:
    def __init__(self, iterations: int = 1, workers: int = 1) -> None:
        self._iterations = iterations
        self._workers = workers
        self._summaries: dict[str, TestSummary] = {}

    @property
    def summaries(self) -> dict[str, TestSummary]:
        return self._summaries

    def run(
        self,
        test_fn: Callable[[], None],
        iterations: int | None = None,
        max_failures: int = 0,
        test_id: str | None = None,
    ) -> bool:
        n = iterations if iterations is not None else self._iterations
        name = getattr(test_fn, "__name__", repr(test_fn))
        with _Spinner(f"{name} — iteration 1/{n}") as spinner:
            result = self.collect(
                test_fn,
                on_iteration=lambda i, _n: spinner.set_label(
                    f"{name} — iteration {i + 1}/{_n}"
                ),
                iterations=n,
                max_failures=max_failures,
            )
        self._report(name, result, test_id)
        return result.passed

    def _report(
        self, name: str, result: _CollectResult, test_id: str | None = None
    ) -> None:
        # Key the persisted summary by a file-qualified id so tests sharing a
        # function name across files don't overwrite one another; the display
        # still shows the bare function name.
        self._summaries[test_id or name] = TestSummary.from_result(result)
        print_test_header(name, result.iterations)
        print_test_results(
            result.check_results,
            result.all_runs,
            result.run_errors,
            result.iterations,
            failed_iterations=result.failed_iterations,
            max_failures=result.max_failures,
        )

    def run_all(self, test_cases: list[TestCase]) -> bool:
        if self._workers <= 1:
            return self._run_sequential(test_cases)
        return self._run_parallel(test_cases)

    def collect(
        self,
        test_fn: Callable[[], None],
        on_iteration: Callable[[int, int], None] | None = None,
        iterations: int | None = None,
        max_failures: int = 0,
    ) -> _CollectResult:
        n = iterations if iterations is not None else self._iterations
        result = _CollectResult(iterations=n, max_failures=max_failures)
        for i in range(n):
            if on_iteration is not None:
                on_iteration(i, n)
            collector, checks, error = self._run_one_iteration(test_fn)
            if error is not None:
                result.run_errors.append(error)
            result.all_runs.extend(collector)
            for label, passed in checks:
                result.check_results[label].append(passed)
            if error is not None or any(not passed for _, passed in checks):
                result.failed_iterations += 1
        return result

    @staticmethod
    def _run_one_iteration(
        test_fn: Callable[[], None],
    ) -> tuple[list[AgentRun], list[tuple[str, bool]], Exception | None]:
        collector: list[AgentRun] = []
        checks: list[tuple[str, bool]] = []
        error: Exception | None = None
        c_token = _active_collector.set(collector)
        ch_token = _active_checks.set(checks)
        try:
            test_fn()
        except Exception as e:
            error = e
        finally:
            _active_collector.reset(c_token)
            _active_checks.reset(ch_token)
        return collector, checks, error

    def _run_sequential(self, test_cases: list[TestCase]) -> bool:
        ok = True
        last_file: Path | None = None
        for tc in test_cases:
            if tc.path != last_file:
                print(f"  {_cyan('──')} {_dim(str(tc.path))}")
                last_file = tc.path
            n = getattr(tc.fn, "_tea_iterations", self._iterations)
            max_failures = getattr(tc.fn, "_tea_max_failures", 0)
            passed = self.run(
                tc.fn, iterations=n, max_failures=max_failures, test_id=tc.id
            )
            ok = ok and passed
        return ok

    def _run_parallel(self, test_cases: list[TestCase]) -> bool:
        total = len(test_cases)
        workers = self._workers
        print(f"  {_cyan('──')} running {total} test(s) with {workers} worker(s)\n")

        completed = 0
        running: set[str] = set()
        lock = threading.Lock()

        def _label() -> str:
            if running:
                return f"{', '.join(sorted(running))}  [{completed}/{total}]"
            return f"{completed}/{total} done"

        def _on_start(name: str) -> None:
            with lock:
                running.add(name)
            spinner.set_label(_label())

        def _work(tc: TestCase) -> _CollectResult:
            name = getattr(tc.fn, "__name__", repr(tc.fn))
            _on_start(name)
            n = getattr(tc.fn, "_tea_iterations", self._iterations)
            max_failures = getattr(tc.fn, "_tea_max_failures", 0)
            return self.collect(tc.fn, iterations=n, max_failures=max_failures)

        ok = True
        futures_map: dict[Future, TestCase] = {}
        executor = ThreadPoolExecutor(max_workers=self._workers)
        try:
            with _Spinner(_label()) as spinner:
                for tc in test_cases:
                    fut = executor.submit(_work, tc)
                    futures_map[fut] = tc

                last_file: Path | None = None
                for fut in as_completed(futures_map):
                    tc = futures_map[fut]
                    name = getattr(tc.fn, "__name__", repr(tc.fn))

                    with lock:
                        running.discard(name)
                    completed += 1
                    spinner.set_label(_label())

                    with spinner.paused():
                        if tc.path != last_file:
                            print(f"  {_cyan('──')} {_dim(str(tc.path))}")
                            last_file = tc.path
                        exc = fut.exception()
                        if exc:
                            ok = False
                            print(f"\n  {_bold_cyan(name)}\n  error: {exc}\n")
                        else:
                            result = fut.result()
                            self._report(name, result, test_id=tc.id)
                            ok = ok and result.passed

        except KeyboardInterrupt:
            Docker.get().shutdown()
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)
            return ok
