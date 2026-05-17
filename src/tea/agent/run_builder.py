from __future__ import annotations

import difflib
import os
import shutil
import tempfile
from typing import Protocol

from tea._context import _active_collector
from tea.tui.metrics import print_metrics

from .agent_run import AgentRun, FileChange, FileDiff


class _Runnable(Protocol):
    def _execute(
        self, text: str, *, timeout: int, workdir: str | None, skills: list[str]
    ) -> AgentRun: ...

    def prepare_skills(self, prompt: str, workdir: str, skills: list[str]) -> str: ...


class RunBuilder:
    @classmethod
    def prompt(cls, runner: _Runnable, text: str, *, timeout: int = 300) -> RunBuilder:
        return cls(runner, text, timeout)

    def __init__(self, runner: _Runnable, text: str, timeout: int) -> None:
        self._runner = runner
        self._text = text
        self._timeout = timeout
        self._workdir: str | None = None

    def workdir(self, path: str) -> RunBuilder:
        self._workdir = os.path.abspath(path)
        return self

    def run(self) -> AgentRun:
        tmp_dir: str | None = None
        if self._workdir:
            tmp_dir = tempfile.mkdtemp()
            shutil.copytree(self._workdir, tmp_dir, dirs_exist_ok=True)
        effective_workdir = tmp_dir if tmp_dir else self._workdir
        skills = _discover_skills(self._workdir)
        text = self._text
        if skills and effective_workdir:
            text = self._runner.prepare_skills(text, effective_workdir, skills)
        try:
            before = _snapshot(self._workdir)
            result = self._runner._execute(
                text, timeout=self._timeout, workdir=effective_workdir, skills=skills
            )
            after = _snapshot(effective_workdir)
            result._files_changed_fn = lambda: _diff_snapshots(before, after)
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


def _discover_skills(workdir: str | None) -> list[str]:
    if not workdir:
        return []
    skills_dir = os.path.join(workdir, ".claude", "skills")
    if not os.path.isdir(skills_dir):
        return []
    return [
        entry.name
        for entry in os.scandir(skills_dir)
        if entry.is_dir() and os.path.isfile(os.path.join(entry.path, "SKILL.md"))
    ]


def _snapshot(path: str | None) -> dict[str, str]:
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
    changes: dict[str, FileChange] = {}
    for fname in set(before) | set(after):
        old, new = before.get(fname, ""), after.get(fname, "")
        if old == new:
            continue
        added_lines, removed_lines, unified_lines = [], [], []
        for line in difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=fname,
            tofile=fname,
            lineterm="",
        ):
            unified_lines.append(line)
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                removed_lines.append(line[1:])
        changes[fname] = FileChange(
            path=fname,
            diff=FileDiff(
                added="".join(added_lines),
                removed="".join(removed_lines),
                unified="\n".join(unified_lines),
            ),
        )
    return changes
