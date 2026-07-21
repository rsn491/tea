from __future__ import annotations

import os
import sys
from typing import Literal, get_args

from .default_theme import DefaultTheme
from .light_theme import LightTheme
from .theme import Theme

Mode = Literal["dark", "light"]

_DEFAULT: Mode = "dark"
_VALID: tuple[Mode, ...] = get_args(Mode)
_THEMES: dict[Mode, type[Theme]] = {"dark": DefaultTheme, "light": LightTheme}

# The active palette every theme helper renders through. Installed once, at
# startup, by set_mode(); defaults to the dark theme until then.
_active: type[Theme] = DefaultTheme


def active_theme() -> type[Theme]:
    """The palette currently in effect."""
    return _active


def resolve_mode(flag: str | None = None) -> Mode:
    """Pick the mode: --theme flag > TEA_THEME env > default 'dark'.

    Each source is tried in precedence order; an unknown value warns and falls
    through to the next source, so a bad flag never masks a valid TEA_THEME.
    """
    for source in (flag, os.environ.get("TEA_THEME")):
        if source is None:
            continue
        value = source.strip().lower()
        if value in _VALID:
            return value  # type: ignore[return-value]
        print(f"tea: unknown theme {source!r}; using {_DEFAULT!r}", file=sys.stderr)
    return _DEFAULT


def set_mode(flag: str | None = None) -> Mode:
    """Resolve and install the active theme mode. Call once, at startup."""
    global _active
    mode = resolve_mode(flag)
    _active = _THEMES[mode]
    return mode
