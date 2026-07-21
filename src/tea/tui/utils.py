from __future__ import annotations

import os
import sys

_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
_NO_SPINNER = os.environ.get("NO_SPINNER") is not None

# Not every terminal renders 24-bit color; Apple Terminal.app, for one, mangles
# `38;2;…` rather than approximating it. Emit truecolor only when COLORTERM
# advertises it, and fall back to the nearest 256-color index otherwise.
_TRUECOLOR = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")


def _c(code: str, text: str) -> str:
    """Wrap text in an ANSI escape sequence; passthrough if not a TTY."""
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _rgb(r: int, g: int, b: int) -> str:
    """ANSI foreground color code — 24-bit when supported, else 256-color."""
    if _TRUECOLOR:
        return f"38;2;{r};{g};{b}"
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
