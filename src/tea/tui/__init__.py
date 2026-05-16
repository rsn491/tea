from __future__ import annotations

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
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        if not _TTY or _NO_SPINNER:
            return
        clear = " " * (_vlen(self._label) + 10)
        for ch in itertools.cycle(self._FRAMES):
            if self._stopped.wait(0.08):
                break
            sys.stdout.write(f"\r  {_cyan(ch)} {self._label} …")
            sys.stdout.flush()
        sys.stdout.write(f"\r{clear}\r")
        sys.stdout.flush()

    def __enter__(self) -> _Spinner:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stopped.set()
        self._thread.join()


# ── row / pass-fail ────────────────────────────────────────────────────────────

_COL = 36
_PASS = _green("✓")
_FAIL = _red("✗")


def _row(symbol: str, name: str, value: str) -> str:
    pad = "." * max(1, _COL - _vlen(name))
    return f"     {symbol} {name}{pad}: {value}"


__all__ = ["print_banner"]
