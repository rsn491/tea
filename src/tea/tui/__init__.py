from __future__ import annotations

import re

from .banner import print_banner
from .spinner import _Spinner
from .theme import error, success

# ── ANSI strip / visible-length ────────────────────────────────────────────────

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _vlen(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


# ── row / pass-fail ────────────────────────────────────────────────────────────

_COL = 36
_PASS = success("✓")
_FAIL = error("✗")


def _row(symbol: str, name: str, value: str) -> str:
    pad = "." * max(1, _COL - _vlen(name))
    return f"     {symbol} {name}{pad}: {value}"


__all__ = ["print_banner", "_Spinner"]
