from __future__ import annotations

import contextlib
import itertools
import os
import re
import sys
import threading

from .banner import print_banner

# ── color helpers ──────────────────────────────────────────────────────────────

_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
_NO_SPINNER = os.environ.get("NO_SPINNER") is not None
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _green(t: str) -> str:
    return _c("32", t)


def _red(t: str) -> str:
    return _c("31", t)


def _cyan(t: str) -> str:
    return _c("36", t)


def _bold(t: str) -> str:
    return _c("1", t)


def _dim(t: str) -> str:
    return _c("2", t)


def _bold_cyan(t: str) -> str:
    return _c("1;36", t)


def _vlen(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


# ── spinner ────────────────────────────────────────────────────────────────────


class _Spinner:
    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label: str) -> None:
        self._label = label
        self._stopped = threading.Event()
        self._paused = threading.Event()  # set → spin thread should pause
        self._cleared = threading.Event()  # set → spin thread has cleared the line
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def set_label(self, label: str) -> None:
        """Update the spinner label (safe to call from any thread)."""
        self._label = label

    def _clear_line(self) -> None:
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()

    def _spin(self) -> None:
        if not _TTY or _NO_SPINNER:
            return
        for ch in itertools.cycle(self._FRAMES):
            if self._stopped.is_set():
                break
            if self._paused.is_set():
                self._clear_line()
                self._cleared.set()
                # Wait until resumed or stopped (poll every 50 ms)
                while self._paused.is_set() and not self._stopped.is_set():
                    self._stopped.wait(0.05)
                self._cleared.clear()
                continue
            sys.stdout.write(f"\r  {_cyan(ch)} {self._label} …")
            sys.stdout.flush()
            self._stopped.wait(0.08)
        self._clear_line()

    def __enter__(self) -> _Spinner:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stopped.set()
        self._thread.join()

    @contextlib.contextmanager
    def paused(self):  # type: ignore[return]
        """Temporarily pause the spinner so the caller can write to stdout cleanly."""
        self._cleared.clear()
        self._paused.set()
        if _TTY and not _NO_SPINNER:
            self._cleared.wait()  # block until the spin thread has cleared the line
        try:
            yield
        finally:
            self._paused.clear()


# ── row / pass-fail ────────────────────────────────────────────────────────────

_COL = 36
_PASS = _green("✓")
_FAIL = _red("✗")


def _row(symbol: str, name: str, value: str) -> str:
    pad = "." * max(1, _COL - _vlen(name))
    return f"     {symbol} {name}{pad}: {value}"


__all__ = ["print_banner"]
