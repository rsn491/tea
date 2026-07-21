from __future__ import annotations

import difflib
import logging
import os
import shutil
import tempfile
from typing import TYPE_CHECKING, Protocol

from tea._context import _active_collector
from tea.tui.metrics import print_metrics

from .agent_run import AgentRun, FileChange, FileDiff

if TYPE_CHECKING:
    from tea.executor import Executor

    from .agent import Agent

_log = logging.getLogger(__name__)


class _Runnable(Protocol):
    _agent: Agent
    _executor: Executor
    skills_sources: list[str] | None
    default_skill_sources: tuple[str, ...]


class RunBuilder:
    @classmethod
    def prompt(cls, runner: _Runnable, text: str, *, timeout: int = 300) -> RunBuilder:
        return cls(runner, text, timeout)

    def __init__(self, runner: _Runnable, text: str, timeout: int) -> None:
        self._runner = runner
        self._text = text
        self._timeout = timeout
        self._workdir: str | None = None
        self._skills_sources: list[str] | None = runner.skills_sources
        self._defaults: tuple[str, ...] = runner.default_skill_sources

    def workdir(self, path: str) -> RunBuilder:
        self._workdir = os.path.abspath(path)
        return self

    def skills_from(self, sources: str | list[str] | None) -> RunBuilder:
        """Override the suite-level skill sources for this single run.

        Accepts a single relative path or a list of relative paths (each
        interpreted relative to the run's ``workdir``). Passing ``[]``
        disables skill loading; passing ``None`` re-enables the agent's
        default discovery.
        """
        if sources is None:
            self._skills_sources = None
        elif isinstance(sources, str):
            self._skills_sources = [sources]
        else:
            self._skills_sources = list(sources)
        return self

    def run(self) -> AgentRun:
        agent = self._runner._agent
        executor = self._runner._executor

        tmp_dir: str | None = None
        if self._workdir:
            tmp_dir = tempfile.mkdtemp()
            # symlinks=False (the default) dereferences symlinks so symlinked
            # skill bundles land in the tmp copy as real files. Required for
            # the bind mount, since symlink targets outside the workdir would
            # be unreachable inside the container.
            shutil.copytree(self._workdir, tmp_dir, dirs_exist_ok=True)
        effective_workdir = tmp_dir if tmp_dir else self._workdir
        sources = _resolve_skill_sources(
            self._skills_sources, self._defaults, effective_workdir
        )
        skills, source_for = _discover_skills(sources, effective_workdir)
        try:
            before = _snapshot(self._workdir)
            spec = agent.build_spec(self._text, self._timeout)
            if skills and effective_workdir:
                spec, _ = agent.install_skills(
                    spec, self._text, effective_workdir, skills, source_for
                )
            raw = executor.run(spec, effective_workdir)
            result = agent.parse(raw)
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


def _resolve_skill_sources(
    skills_sources: list[str] | None,
    defaults: tuple[str, ...],
    workdir: str | None,
) -> list[str]:
    """Decide which source paths to scan.

    Rules:
    * ``skills_sources is None``: fall back to the agent's defaults, filtered
      to those that exist on disk under ``workdir`` (conventional paths are a
      hint, not a contract — missing ones are silently skipped).
    * ``skills_sources == []``: explicit opt-out, no skills loaded.
    * Otherwise: use the supplied list verbatim. Each path is validated as
      relative; missing paths raise (explicit means explicit).
    """
    if not workdir:
        return []
    if skills_sources is None:
        return [src for src in defaults if os.path.isdir(os.path.join(workdir, src))]
    if not skills_sources:
        return []
    for src in skills_sources:
        if os.path.isabs(src):
            raise ValueError(
                f"skill source must be relative to workdir; got absolute path {src!r}"
            )
        if not os.path.isdir(os.path.join(workdir, src)):
            raise ValueError(
                f"skill source {src!r} does not exist under workdir {workdir!r}"
            )
    return list(skills_sources)


def _discover_skills(
    sources: list[str], workdir: str | None
) -> tuple[list[str], dict[str, str]]:
    """Scan each source for ``<source>/*/SKILL.md`` directories.

    Returns ``(skills, source_for)`` where ``skills`` is the ordered list of
    discovered skill names and ``source_for`` maps each name to the source it
    was found in. When the same skill name appears in multiple sources, the
    earlier source wins (and the later occurrence is logged and skipped).
    """
    if not workdir or not sources:
        return [], {}
    skills: list[str] = []
    source_for: dict[str, str] = {}
    for src in sources:
        full = os.path.join(workdir, src)
        if not os.path.isdir(full):
            continue
        for entry in os.scandir(full):
            if not entry.is_dir():
                continue
            if not os.path.isfile(os.path.join(entry.path, "SKILL.md")):
                continue
            name = entry.name
            if name in source_for:
                _log.info(
                    "skill %r already discovered in %r; skipping duplicate in %r",
                    name,
                    source_for[name],
                    src,
                )
                continue
            skills.append(name)
            source_for[name] = src
    return skills, source_for


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
