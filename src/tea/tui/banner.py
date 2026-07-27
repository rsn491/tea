from __future__ import annotations

import os
import sys

_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _dim(t: str) -> str:
    return _c("2", t)


def _bold_cyan(t: str) -> str:
    return _c("1;36", t)


def print_banner() -> None:
    b = _bold_cyan
    d = _dim
    row1 = b("   __            ")
    row2 = b("  / /____  ____ _")
    row3 = b(" / __/ _ \\/ __ `/")
    row4 = b("/ /_/  __/ /_/ / ")
    row5 = b("\\__/\\___/\\__,_/  ")
    tagline = d("testing and evaluation for agents")
    print(
        f"""
{row1}
{row2}
{row3}  {tagline}
{row4}
{row5}
"""
    )
