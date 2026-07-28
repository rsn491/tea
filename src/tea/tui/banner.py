from __future__ import annotations

from .theme import bold_primary_light, dim


def print_banner() -> None:
    b = bold_primary_light
    d = dim
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
