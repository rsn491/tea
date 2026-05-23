from __future__ import annotations

import importlib.util
import sys
import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from types import ModuleType
from typing import Callable

from tea._context import _active_checks, _active_collector
from tea.agent.agent_run import AgentRun
from tea.infra.docker import Docker
from tea.tui import _bold_cyan, _cyan, _dim, _Spinner
from tea.tui.runner_view import print_test_header, print_test_results


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


def run(target: str, default_iterations: int = 1, workers: int = 1) -> None:
    if "::" in target:
        file_part, fn_name = target.split("::", 1)
        path = Path(file_part)
        module = load_module(path)
        fn = getattr(module, fn_name, None)
        if fn is None:
            print(f"tea: '{fn_name}' not found in {file_part}")
            sys.exit(1)
        test_cases = [(path, fn)]
    else:
        path = Path(target)
        test_cases = [
            (f, fn)
            for f in discover_test_files(path)
            for fn in collect_fns(load_module(f))
        ]

    if not test_cases:
        print(f"tea: no tests found in '{target}'")
        sys.exit(1)

    if workers <= 1:
        _run_sequential(test_cases, default_iterations)
    else:
        _run_parallel(test_cases, default_iterations, workers)


def _run_sequential(
    test_cases: list[tuple[Path, Callable]], default_iterations: int
) -> None:
    last_file: Path | None = None
    for file_path, fn in test_cases:
        if file_path != last_file:
            print(f"  {_cyan('──')} {_dim(str(file_path))}")
            last_file = file_path
        n = getattr(fn, "_tea_iterations", default_iterations)
        TestRunner(iterations=n).run(fn)


def _run_one_test(
    fn: Callable,
    default_iterations: int,
    on_start: Callable[[], None] | None = None,
) -> tuple[dict[str, list[bool]], list[AgentRun], list[Exception], int]:
    """Run all iterations of one test function, collecting results without printing."""
    if on_start is not None:
        on_start()
    n = getattr(fn, "_tea_iterations", default_iterations)
    all_runs: list[AgentRun] = []
    check_results: dict[str, list[bool]] = defaultdict(list)
    run_errors: list[Exception] = []

    for _ in range(n):
        collector: list[AgentRun] = []
        checks: list[tuple[str, bool]] = []
        c_token = _active_collector.set(collector)
        ch_token = _active_checks.set(checks)
        try:
            fn()
        except Exception as e:
            run_errors.append(e)
        finally:
            _active_collector.reset(c_token)
            _active_checks.reset(ch_token)
        all_runs.extend(collector)
        for label, passed in checks:
            check_results[label].append(passed)

    return check_results, all_runs, run_errors, n


def _run_parallel(
    test_cases: list[tuple[Path, Callable]],
    default_iterations: int,
    workers: int,
) -> None:
    """Run test cases concurrently; print each test's results as it finishes."""
    total = len(test_cases)
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

    futures_map: dict[Future, tuple[Path, Callable]] = {}
    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        with _Spinner(_label()) as spinner:
            for file_path, fn in test_cases:
                name = getattr(fn, "__name__", repr(fn))
                fut = executor.submit(
                    _run_one_test,
                    fn,
                    default_iterations,
                    lambda n=name: _on_start(n),
                )
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
                        check_results, all_runs, run_errors, n = fut.result()
                        print_test_header(name, n)
                        print_test_results(check_results, all_runs, run_errors, n)

    except KeyboardInterrupt:
        Docker.get().shutdown()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)


def iterations(n: int) -> Callable:
    """Decorator to set the default iteration count for a test function."""

    def decorator(fn: Callable) -> Callable:
        fn._tea_iterations = n
        return fn

    return decorator


class TestRunner:
    def __init__(self, iterations: int = 1) -> None:
        self._iterations = iterations

    def run(self, test_fn: Callable[[], None]) -> None:
        name = getattr(test_fn, "__name__", repr(test_fn))
        print_test_header(name, self._iterations)

        all_runs: list[AgentRun] = []
        check_results: dict[str, list[bool]] = defaultdict(list)
        run_errors: list[Exception] = []

        try:
            for i in range(self._iterations):
                collector: list[AgentRun] = []
                checks: list[tuple[str, bool]] = []
                c_token = _active_collector.set(collector)
                ch_token = _active_checks.set(checks)
                spin_label = f"iteration {i + 1}/{self._iterations}"
                with _Spinner(spin_label):
                    try:
                        test_fn()
                    except Exception as e:
                        run_errors.append(e)
                    finally:
                        _active_collector.reset(c_token)
                        _active_checks.reset(ch_token)
                all_runs.extend(collector)
                for check_label, passed in checks:
                    check_results[check_label].append(passed)
        except KeyboardInterrupt:
            if check_results or all_runs:
                print_test_results(check_results, all_runs, run_errors, i + 1)
            raise

        print_test_results(check_results, all_runs, run_errors, self._iterations)
