from __future__ import annotations

import os
import sys

_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
_NO_SPINNER = os.environ.get("NO_SPINNER") is not None


def _c(code: str, text: str) -> str:
    """Wrap text in an ANSI escape sequence; passthrough if not a TTY."""
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _rgb(r: int, g: int, b: int) -> str:
    """256-color ANSI foreground code nearest to the given RGB triple.

    We target 256-color rather than 24-bit truecolor for portability — not
    every terminal renders `38;2;…` correctly (Apple Terminal.app mangles it).
    """
    return f"38;5;{_nearest_256(r, g, b)}"


def _nearest_256(r: int, g: int, b: int) -> int:
    """Map an RGB triple to the closest xterm-256 palette index."""
    if r == g == b:  # grayscale ramp (232–255), with cube endpoints for extremes
        if r < 8:
            return 16
        if r > 248:
            return 231
        return 232 + round((r - 8) / 247 * 24)

    def _cube(c: int) -> int:
        return 0 if c < 48 else 1 if c < 115 else (c - 35) // 40

    return 16 + 36 * _cube(r) + 6 * _cube(g) + _cube(b)


def bold(t: str) -> str:
    """Apply bold formatting."""
    return _c("1", t)


def dim(t: str) -> str:
    """Apply dim formatting."""
    return _c("2", t)
