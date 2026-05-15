from __future__ import annotations

import os
import sys

_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _cyan(t: str) -> str:
    return _c("36", t)


def _dim(t: str) -> str:
    return _c("2", t)


def _bold_cyan(t: str) -> str:
    return _c("1;36", t)


def print_banner() -> None:
    c = _cyan
    b = _bold_cyan
    d = _dim
    cup = c("\\_____/")
    base = c("\\_________/")
    print(
        f"""\n     {c("( (")}
   {c("[o _ o]~")}  {b("tea")} {d("| testing and evaluation for agents")}
   {cup}       {d("")}
 {base}\n
"""
    )
