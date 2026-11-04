"""RunBuilder workdir copy, change detection and cleanup."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

import pytest

from tea.agent import run_builder
from tea.agent.agent_run import AgentRun
from tea.agent.run_builder import (
    RunBuilder,
    _changed_contents,
    _copy_workdir,
    _diff_snapshots,
)


class _Runner:
    """Harness stand-in whose run applies ``mutate`` to the workdir copy."""

    skills_sources: list[str] | None = []
    default_skill_sources: tuple[str, ...] = ()

    def __init__(self, mutate: Callable[[str], None]) -> None:
        self._mutate = mutate
        self.workdir: str | None = None

    def _execute(self, text, *, timeout, workdir, skills, source_for) -> AgentRun:
        self.workdir = workdir
        self._mutate(workdir)
        return AgentRun(raw="", steps=[], tools=[], skills=[])


def _write(path, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def _run(workdir, mutate: Callable[[str], None]) -> tuple[AgentRun, _Runner]:
    runner = _Runner(mutate)
    run = RunBuilder.prompt(runner, "x").workdir(str(workdir)).run()
    run_builder._cleanup_pool.submit(lambda: None).result()  # drain cleanup
    return run, runner


@pytest.fixture
def workdir(tmp_path):
    wd = tmp_path / "wd"
    _write(str(wd / "keep.txt"), "same\n")
    _write(str(wd / "edit.txt"), "old\n")
    _write(str(wd / "gone.txt"), "bye\n")
    _write(str(wd / "pkg" / "deep.txt"), "deep\n")
    _write(str(wd / ".hidden" / "h.txt"), "h\n")
    return wd


def test_detects_modify_add_delete_and_ignores_untouched(workdir):
    def mutate(wd):
        _write(os.path.join(wd, "edit.txt"), "new\n")
        _write(os.path.join(wd, "pkg", "added.txt"), "hi\n")
        os.remove(os.path.join(wd, "gone.txt"))

    run, _ = _run(workdir, mutate)

    assert set(run.files_changed) == {"edit.txt", "pkg/added.txt", "gone.txt"}
    assert run.files_changed["edit.txt"].diff.added == "new\n"
    assert run.files_changed["edit.txt"].diff.removed == "old\n"
    assert run.files_changed["pkg/added.txt"].diff.added == "hi\n"
    assert run.files_changed["gone.txt"].diff.removed == "bye\n"


def test_detects_same_size_rewrite(workdir):
    run, _ = _run(workdir, lambda wd: _write(os.path.join(wd, "edit.txt"), "OLD\n"))

    assert set(run.files_changed) == {"edit.txt"}


def test_touch_without_content_change_is_not_reported(workdir):
    run, _ = _run(workdir, lambda wd: _write(os.path.join(wd, "keep.txt"), "same\n"))

    assert run.files_changed == {}


def test_hidden_dirs_are_ignored(workdir):
    def mutate(wd):
        _write(os.path.join(wd, ".hidden", "h.txt"), "changed\n")
        _write(os.path.join(wd, ".claude", "skills", "s", "SKILL.md"), "# s\n")

    run, _ = _run(workdir, mutate)

    assert run.files_changed == {}


def test_symlinked_dir_is_not_reported_as_added(tmp_path):
    external = tmp_path / "external"
    _write(str(external / "lib.txt"), "lib\n")
    wd = tmp_path / "wd"
    wd.mkdir()
    os.symlink(str(external), str(wd / "vendor"))

    run, _ = _run(wd, lambda _: None)

    assert run.files_changed == {}


def test_original_workdir_untouched_and_copy_removed(workdir):
    run, runner = _run(
        workdir, lambda wd: _write(os.path.join(wd, "edit.txt"), "new\n")
    )

    assert (workdir / "edit.txt").read_text() == "old\n"
    assert runner.workdir is not None
    assert not os.path.exists(runner.workdir)
    # Diff contents were captured before the copy was deleted.
    assert run.files_changed["edit.txt"].diff.added == "new\n"


def test_copy_removed_when_execute_raises(workdir):
    seen: dict[str, str] = {}

    def boom(wd):
        seen["wd"] = wd
        raise RuntimeError("agent failed")

    with pytest.raises(RuntimeError):
        _run(workdir, boom)
    run_builder._cleanup_pool.submit(lambda: None).result()

    assert not os.path.exists(seen["wd"])


def test_coarse_timestamps_fall_back_to_content_compare(tmp_path):
    original, copy = tmp_path / "o", tmp_path / "c"
    _write(str(original / "a.txt"), "old\n")
    _write(str(copy / "a.txt"), "new\n")
    _write(str(original / "b.txt"), "same\n")
    _write(str(copy / "b.txt"), "same\n")
    # Whole-second ctimes and identical stats: stats can't be trusted.
    stats = {"a.txt": (4, 0, 1_000_000_000, 1), "b.txt": (5, 0, 1_000_000_000, 2)}

    before, after = _changed_contents(str(original), str(copy), stats, stats)

    assert set(_diff_snapshots(before, after)) == {"a.txt"}


def test_fine_timestamps_skip_unchanged_stats(tmp_path):
    original, copy = tmp_path / "o", tmp_path / "c"
    _write(str(original / "a.txt"), "old\n")
    _write(str(copy / "a.txt"), "new\n")
    stats = {"a.txt": (4, 0, 1_000_000_001, 1)}

    before, after = _changed_contents(str(original), str(copy), stats, stats)

    assert before == {} and after == {}


def test_copy_falls_back_to_copytree_when_cp_fails(tmp_path, monkeypatch):
    src, dst = tmp_path / "src", tmp_path / "dst"
    _write(str(src / "a" / "b.txt"), "b\n")
    dst.mkdir()

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "cp", stderr=b"unsupported")

    monkeypatch.setattr(run_builder.sys, "platform", "linux")
    monkeypatch.setattr(run_builder.subprocess, "run", fail)

    _copy_workdir(str(src), str(dst))

    assert (dst / "a" / "b.txt").read_text() == "b\n"


def test_copy_uses_copytree_off_linux(tmp_path, monkeypatch):
    src, dst = tmp_path / "src", tmp_path / "dst"
    _write(str(src / "a.txt"), "a\n")
    dst.mkdir()

    def unexpected(*args, **kwargs):
        raise AssertionError("cp must not be used off Linux")

    monkeypatch.setattr(run_builder.sys, "platform", "darwin")
    monkeypatch.setattr(run_builder.subprocess, "run", unexpected)

    _copy_workdir(str(src), str(dst))

    assert (dst / "a.txt").read_text() == "a\n"
