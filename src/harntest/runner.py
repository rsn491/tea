from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Callable

from harntest._context import _active_checks, _active_collector
from harntest.agent.agent_run import AgentRun
from harntest.tui import _Spinner, _cyan, _dim
from harntest.tui.runner_view import print_test_header, print_test_results


def discover_test_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("test_*.py"))


def load_module(path: Path) -> ModuleType:
    parent = str(path.parent.resolve())
    if parent not in sys.path:
        sys.path.insert(0, parent)
    spec = importlib.util.spec_from_file_location(path.stem, path.resolve())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect_fns(module: ModuleType) -> list[Callable]:
    return [
        obj
        for name, obj in vars(module).items()
        if name.startswith("test_") and callable(obj)
    ]


def run(target: str, default_iterations: int = 1) -> None:
    if "::" in target:
        file_part, fn_name = target.split("::", 1)
        path = Path(file_part)
        module = load_module(path)
        fn = getattr(module, fn_name, None)
        if fn is None:
            print(f"harntest: '{fn_name}' not found in {file_part}")
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
        print(f"harntest: no tests found in '{target}'")
        sys.exit(1)

    last_file: Path | None = None
    for file_path, fn in test_cases:
        if file_path != last_file:
            print(f"  {_cyan('──')} {_dim(str(file_path))}")
            last_file = file_path
        n = getattr(fn, "_harntest_iterations", default_iterations)
        TestRunner(iterations=n).run(fn)


def iterations(n: int) -> Callable:
    """Decorator to set the default iteration count for a test function."""

    def decorator(fn: Callable) -> Callable:
        fn._harntest_iterations = n
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

        print_test_results(check_results, all_runs, run_errors, self._iterations)
