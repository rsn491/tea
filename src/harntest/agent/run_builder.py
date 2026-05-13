"""Builder API for executing an agent prompt in an isolated workspace."""

from __future__ import annotations

import difflib
import os
import shutil
import tempfile

from harntest._context import _active_collector
from harntest.tui.metrics import print_metrics
from .agent_run import AgentRun, FileChange, FileDiff
from .agent_runner import AgentRunner


class RunBuilder:
    """Fluent builder for configuring and running one agent prompt."""

    @classmethod
    def prompt(
        cls, runner: AgentRunner, text: str, *, timeout: int = 300
    ) -> RunBuilder:
        """Create a new prompt builder."""
        return cls(runner, text, timeout)

    def __init__(self, runner: AgentRunner, text: str, timeout: int) -> None:
        self._runner = runner
        self._text = text
        self._timeout = timeout
        self._workdir: str | None = None

    def workdir(self, path: str) -> RunBuilder:
        """Run the prompt against a copied working directory."""
        self._workdir = os.path.abspath(path)
        return self

    def run(self) -> AgentRun:
        """Execute and return the parsed run result."""
        tmp_dir: str | None = None
        if self._workdir:
            tmp_dir = tempfile.mkdtemp()
            shutil.copytree(self._workdir, tmp_dir, dirs_exist_ok=True)
        effective_workdir = tmp_dir if tmp_dir else self._workdir
        try:
            before = _snapshot(self._workdir)
            result = self._runner.execute(
                self._text, timeout=self._timeout, workdir=effective_workdir
            )
            after = _snapshot(effective_workdir)
            result.set_files_changed_resolver(lambda: _diff_snapshots(before, after))
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        collector = _active_collector.get(None)
        if collector is not None:
            collector.append(result)
        else:
            print_metrics(result)
        return result


# helpers


def _snapshot(path: str | None) -> dict[str, str]:
    """Return a text snapshot of all non-hidden files under a path."""
    if not path:
        return {}
    snapshot: dict[str, str] = {}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            abs_path = os.path.join(root, fname)
            rel_path = os.path.relpath(abs_path, path)
            try:
                with open(abs_path, encoding="utf-8", errors="replace") as fh:
                    snapshot[rel_path] = fh.read()
            except OSError:
                pass
    return snapshot


def _diff_snapshots(
    before: dict[str, str], after: dict[str, str]
) -> dict[str, FileChange]:
    """Compute per-file added and removed lines between snapshots."""
    changes: dict[str, FileChange] = {}
    for fname in set(before) | set(after):
        old, new = before.get(fname, ""), after.get(fname, "")
        if old == new:
            continue
        added_lines, removed_lines = [], []
        for line in difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            lineterm="",
        ):
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                removed_lines.append(line[1:])
        changes[fname] = FileChange(
            path=fname,
            diff=FileDiff(added="".join(added_lines), removed="".join(removed_lines)),
        )
    return changes
