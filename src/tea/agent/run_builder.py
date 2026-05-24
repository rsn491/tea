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
    skills_dir: str | None

    def _execute(
        self,
        text: str,
        *,
        timeout: int,
        workdir: str | None,
        skills: list[str],
        skills_dir: str | None,
    ) -> AgentRun: ...


class RunBuilder:
    @classmethod
    def prompt(cls, runner: _Runnable, text: str, *, timeout: int = 300) -> RunBuilder:
        return cls(runner, text, timeout)

    def __init__(self, runner: _Runnable, text: str, timeout: int) -> None:
        self._runner = runner
        self._text = text
        self._timeout = timeout
        self._workdir: str | None = None
        self._skills_dir: str | None = getattr(runner, "skills_dir", None)

    def workdir(self, path: str) -> RunBuilder:
        self._workdir = os.path.abspath(path)
        return self

    def skills_from(self, path: str) -> RunBuilder:
        """Override the suite-level ``skills_dir`` for this single run.

        ``path`` is interpreted relative to the run's ``workdir`` (the same
        convention as the harness-level ``skills_dir``).
        """
        self._skills_dir = path
        return self

    def run(self) -> AgentRun:
        tmp_dir: str | None = None
        if self._workdir:
            tmp_dir = tempfile.mkdtemp()
            shutil.copytree(self._workdir, tmp_dir, dirs_exist_ok=True)
        effective_workdir = tmp_dir if tmp_dir else self._workdir
        skills = _discover_skills(self._skills_dir, effective_workdir)
        try:
            before = _snapshot(self._workdir)
            result = self._runner._execute(
                self._text,
                timeout=self._timeout,
                workdir=effective_workdir,
                skills=skills,
                skills_dir=self._skills_dir,
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


def _discover_skills(skills_dir: str | None, workdir: str | None) -> list[str]:
    """Scan ``<workdir>/<skills_dir>/*/SKILL.md`` and return the skill names.

    ``skills_dir`` is the user-supplied source path; tea imposes no default. If
    either argument is missing, no skills are loaded. Absolute ``skills_dir``
    paths are rejected — skills must live inside the workdir so they ride the
    workdir bind mount into the container.
    """
    if not skills_dir or not workdir:
        return []
    if os.path.isabs(skills_dir):
        raise ValueError(
            f"skills_dir must be relative to workdir; got absolute path {skills_dir!r}"
        )
    full = os.path.join(workdir, skills_dir)
    if not os.path.isdir(full):
        return []
    return [
        entry.name
        for entry in os.scandir(full)
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
