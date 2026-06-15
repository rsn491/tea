from __future__ import annotations

from ..utils import _c, bold
from .default_theme import DefaultTheme

# ── primary helpers ────────────────────────────────────────────────────────────


def primary(t: str) -> str:
    return DefaultTheme.primary(t)


def bold_primary(t: str) -> str:
    return bold(DefaultTheme.primary(t))


def bold_primary_light(t: str) -> str:
    return bold(DefaultTheme.primary_light(t))


# ── utility ────────────────────────────────────────────────────────────────────


def success(t: str) -> str:
    return DefaultTheme.success(t)


def error(t: str) -> str:
    return DefaultTheme.error(t)


def warning(t: str) -> str:
    return _c("33", t)
