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
    print(
        f"""
           {c("⚗")}
           {c("│")}
    {c("╔═════════════╗")}
    {c("║")}  {d("[")}{b("◉")}{d("]")}   {d("[")}{b("◉")}{d("]")}  {c("║")}
    {c("║")}     {d("───")}     {c("║")}
    {c("╚══════╤══════╝")}
    {c("╔══════╧══════╗")}
    {c("║")}   {b("harntest")}  {c("║")}
    {c("║")} {d("agent tester")}{c("║")}
    {c("╚═════════════╝")}
"""
    )
