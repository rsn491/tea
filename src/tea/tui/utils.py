from __future__ import annotations

import os
import sys

_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    """Wrap text in an ANSI escape sequence; passthrough if not a TTY."""
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _rgb(r: int, g: int, b: int) -> str:
    """Return a 24-bit ANSI foreground color code."""
    return f"38;2;{r};{g};{b}"


def bold(t: str) -> str:
    """Apply bold formatting."""
    return _c("1", t)


def dim(t: str) -> str:
    """Apply dim formatting."""
    return _c("2", t)
