from __future__ import annotations

import importlib.util
import sys
import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Callable

from tea._context import _active_checks, _active_collector
from tea.agent.agent_run import AgentRun
from tea.infra.docker import Docker
from tea.tui import _bold_cyan, _cyan, _dim, _Spinner
from tea.tui.runner_view import print_test_header, print_test_results


def _empty_check_results() -> dict[str, list[bool]]:
    return defaultdict(list)


@dataclass
class _CollectResult:
    check_results: dict[str, list[bool]] = field(default_factory=_empty_check_results)
    all_runs: list[AgentRun] = field(default_factory=list)
    run_errors: list[Exception] = field(default_factory=list)
    iterations: int = 0


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


def _discover_test_cases(target: str) -> list[tuple[Path, Callable]]:
    if "::" in target:
        file_part, fn_name = target.split("::", 1)
        path = Path(file_part)
        module = load_module(path)
        fn = getattr(module, fn_name, None)
        if fn is None:
            print(f"tea: '{fn_name}' not found in {file_part}")
            sys.exit(1)
        return [(path, fn)]

    path = Path(target)
    return [
        (f, fn) for f in discover_test_files(path) for fn in collect_fns(load_module(f))
    ]


def run(target: str, default_iterations: int = 1, workers: int = 1) -> None:
    test_cases = _discover_test_cases(target)
    if not test_cases:
        print(f"tea: no tests found in '{target}'")
        sys.exit(1)
    TestRunner(iterations=default_iterations, workers=workers).run_all(test_cases)


def iterations(n: int) -> Callable:
    """Decorator to set the default iteration count for a test function."""

    def decorator(fn: Callable) -> Callable:
        fn._tea_iterations = n
        return fn

    return decorator


class TestRunner:
    def __init__(self, iterations: int = 1, workers: int = 1) -> None:
        self._iterations = iterations
        self._workers = workers

    def run(self, test_fn: Callable[[], None], iterations: int | None = None) -> None:
        n = iterations if iterations is not None else self._iterations
        name = getattr(test_fn, "__name__", repr(test_fn))
        with _Spinner(f"{name} — iteration 1/{n}") as spinner:
            result = self.collect(
                test_fn,
                on_iteration=lambda i, _n: spinner.set_label(
                    f"{name} — iteration {i + 1}/{_n}"
                ),
                iterations=n,
            )
        self._report(name, result)

    @staticmethod
    def _report(name: str, result: _CollectResult) -> None:
        print_test_header(name, result.iterations)
        print_test_results(
            result.check_results,
            result.all_runs,
            result.run_errors,
            result.iterations,
        )

    def run_all(self, test_cases: list[tuple[Path, Callable]]) -> None:
        if self._workers <= 1:
            self._run_sequential(test_cases)
        else:
            self._run_parallel(test_cases)

    def collect(
        self,
        test_fn: Callable[[], None],
        on_iteration: Callable[[int, int], None] | None = None,
        iterations: int | None = None,
    ) -> _CollectResult:
        n = iterations if iterations is not None else self._iterations
        result = _CollectResult(iterations=n)
        for i in range(n):
            if on_iteration is not None:
                on_iteration(i, n)
            collector, checks = self._run_one_iteration(test_fn, result.run_errors)
            result.all_runs.extend(collector)
            for label, passed in checks:
                result.check_results[label].append(passed)
        return result

    @staticmethod
    def _run_one_iteration(
        test_fn: Callable[[], None], run_errors: list[Exception]
    ) -> tuple[list[AgentRun], list[tuple[str, bool]]]:
        collector: list[AgentRun] = []
        checks: list[tuple[str, bool]] = []
        c_token = _active_collector.set(collector)
        ch_token = _active_checks.set(checks)
        try:
            test_fn()
        except Exception as e:
            run_errors.append(e)
        finally:
            _active_collector.reset(c_token)
            _active_checks.reset(ch_token)
        return collector, checks

    def _run_sequential(self, test_cases: list[tuple[Path, Callable]]) -> None:
        last_file: Path | None = None
        for file_path, fn in test_cases:
            if file_path != last_file:
                print(f"  {_cyan('──')} {_dim(str(file_path))}")
                last_file = file_path
            n = getattr(fn, "_tea_iterations", self._iterations)
            self.run(fn, iterations=n)

    def _run_parallel(self, test_cases: list[tuple[Path, Callable]]) -> None:
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

        def _work(fn: Callable) -> _CollectResult:
            name = getattr(fn, "__name__", repr(fn))
            _on_start(name)
            n = getattr(fn, "_tea_iterations", self._iterations)
            return self.collect(fn, iterations=n)

        futures_map: dict[Future, tuple[Path, Callable]] = {}
        executor = ThreadPoolExecutor(max_workers=self._workers)
        try:
            with _Spinner(_label()) as spinner:
                for file_path, fn in test_cases:
                    fut = executor.submit(_work, fn)
                    futures_map[fut] = (file_path, fn)

                last_file: Path | None = None
                for fut in as_completed(futures_map):
                    file_path, fn = futures_map[fut]
                    name = getattr(fn, "__name__", repr(fn))

                    with lock:
                        running.discard(name)
                    completed += 1
                    spinner.set_label(_label())

                    with spinner.paused():
                        if file_path != last_file:
                            print(f"  {_cyan('──')} {_dim(str(file_path))}")
                            last_file = file_path
                        exc = fut.exception()
                        if exc:
                            print(f"\n  {_bold_cyan(name)}\n  error: {exc}\n")
                        else:
                            self._report(name, fut.result())

        except KeyboardInterrupt:
            Docker.get().shutdown()
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)
