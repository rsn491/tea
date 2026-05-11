from __future__ import annotations

import difflib
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from typing import Callable

from harntest.docker import DockerRunConfig, run_in_docker
from harntest.models import AgentRun, FileChange, FileDiff, SandboxResult
from harntest.parsers import claude as _claude_parser
from harntest.parsers import codex as _codex_parser

_CLAUDE_IMAGE = "node:22"
_CODEX_IMAGE = "node:22"
_CONTAINER_WORKDIR = "/workspace"


class Sandbox:
    def __init__(self, image: str, workdir: str | None) -> None:
        self._image = image
        self._workdir = workdir

    def run(self, cmd: list[str]) -> SandboxResult:
        volumes: dict[str, str] = {}
        container_cwd: str | None = None
        if self._workdir:
            volumes[self._workdir] = _CONTAINER_WORKDIR
            container_cwd = _CONTAINER_WORKDIR
        config = DockerRunConfig(
            image=self._image,
            command=cmd,
            volumes=volumes,
            container_workdir=container_cwd,
            timeout=60,
        )
        result = run_in_docker(config)
        return SandboxResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
        )


_DEFAULT_MAX_TURNS = 25


class RunBuilder:
    def __init__(self, runner: _BaseRunner, text: str, timeout: int) -> None:
        self._runner = runner
        self._text = text
        self._timeout = timeout
        self._workdir: str | None = None
        self._after_finished: Callable[[Sandbox], object] | None = None
        self._max_turns: int = _DEFAULT_MAX_TURNS

    def workdir(self, path: str) -> RunBuilder:
        self._workdir = os.path.abspath(path)
        return self

    def maxTurns(self, n: int) -> RunBuilder:
        self._max_turns = n
        return self

    def afterFinished(self, callback: Callable[[Sandbox], object]) -> RunBuilder:
        self._after_finished = callback
        return self

    def run(self) -> AgentRun:
        tmp_dir: str | None = None
        if self._workdir:
            tmp_dir = tempfile.mkdtemp()
            shutil.copytree(self._workdir, tmp_dir, dirs_exist_ok=True)
        effective_workdir = tmp_dir if tmp_dir else self._workdir
        try:
            before = _snapshot(self._workdir)
            result = self._runner._execute(self._text, timeout=self._timeout, workdir=effective_workdir, max_turns=self._max_turns)
            result.files_changed = _diff_snapshots(before, _snapshot(effective_workdir))
            if self._after_finished is not None:
                self._after_finished(Sandbox(self._runner._image, effective_workdir))
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        _print_metrics(result)
        return result


class _BaseRunner(ABC):
    def prompt(self, text: str, *, timeout: int = 300) -> RunBuilder:
        return RunBuilder(self, text, timeout)

    @abstractmethod
    def _execute(self, text: str, *, timeout: int, workdir: str | None, max_turns: int) -> AgentRun: ...


class ClaudeCodeRunner(_BaseRunner):
    _image = _CLAUDE_IMAGE

    def _execute(self, text: str, *, timeout: int, workdir: str | None, max_turns: int) -> AgentRun:
        env: dict[str, str] = {}
        api_key = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if api_key:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = api_key

        volumes: dict[str, str] = {}
        container_cwd: str | None = None
        if workdir:
            volumes[workdir] = _CONTAINER_WORKDIR
            container_cwd = _CONTAINER_WORKDIR

        # Run as non-root: --dangerously-skip-permissions is blocked for root.
        # node:22 ships a `node` user; install to a user-local npm prefix so
        # root write access to /usr/local is not required.
        _npm_prefix = "/home/node/.npm-global"
        env["HOME"] = "/home/node"
        env["NPM_CONFIG_PREFIX"] = _npm_prefix
        run_cmd = (
            f"npm install -g @anthropic-ai/claude-code --quiet 2>/dev/null"
            f" && {_npm_prefix}/bin/claude --dangerously-skip-permissions"
            f" --model claude-haiku-4-5-20251001 --max-turns {max_turns}"
            f' --print --output-format stream-json --verbose "{_esc(text)}"'
        )
        config = DockerRunConfig(
            image=_CLAUDE_IMAGE,
            command=["sh", "-c", run_cmd],
            env=env,
            timeout=timeout,
            volumes=volumes,
            container_workdir=container_cwd,
            user="node",
        )
        result = run_in_docker(config)
        run = _claude_parser.parse(result.stdout)
        run.exit_code = result.exit_code
        run.stderr = result.stderr
        run.duration_s = result.duration_s
        return run


class CodexRunner(_BaseRunner):
    _image = _CODEX_IMAGE

    def _execute(self, text: str, *, timeout: int, workdir: str | None, max_turns: int) -> AgentRun:
        env: dict[str, str] = {}
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            env["OPENAI_API_KEY"] = api_key

        volumes: dict[str, str] = {}
        container_cwd: str | None = None
        if workdir:
            volumes[workdir] = _CONTAINER_WORKDIR
            container_cwd = _CONTAINER_WORKDIR

        run_cmd = (
            "npm install -g @openai/codex --quiet 2>/dev/null"
            f' && codex --approval-mode full-auto --max-turns {max_turns} "{_esc(text)}"'
        )
        config = DockerRunConfig(
            image=_CODEX_IMAGE,
            command=["sh", "-c", run_cmd],
            env=env,
            timeout=timeout,
            volumes=volumes,
            container_workdir=container_cwd,
        )
        result = run_in_docker(config)
        run = _codex_parser.parse(result.stdout)
        run.exit_code = result.exit_code
        run.stderr = result.stderr
        run.duration_s = result.duration_s
        return run


# ── helpers ──────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")


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


_COL = 30


def _metric_line(name: str, value: str) -> str:
    dots = "." * (_COL - len(name))
    return f"  {name}{dots}: {value}"


def _print_metrics(run: AgentRun) -> None:
    duration_str = f"{run.duration_s:.1f}s"
    lines = [
        "",
        _metric_line("step_count", str(run.step_count)),
        _metric_line("token_count", str(run.token_count)),
        _metric_line("duration", duration_str),
        _metric_line("exit_code", str(run.exit_code)),
        "",
    ]
    print("\n".join(lines))
    if run.stderr:
        print("[stderr]", run.stderr)


class Agent:
    ClaudeCode: _BaseRunner = ClaudeCodeRunner()
    Codex: _BaseRunner = CodexRunner()
