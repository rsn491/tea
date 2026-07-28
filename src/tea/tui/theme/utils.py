from __future__ import annotations

from ..utils import bold
from .active import active_theme

# ── primary helpers ────────────────────────────────────────────────────────────


def primary(t: str) -> str:
    return active_theme().primary(t)


def bold_primary(t: str) -> str:
    return bold(active_theme().primary(t))


def bold_primary_light(t: str) -> str:
    return bold(active_theme().primary_light(t))


# ── utility ────────────────────────────────────────────────────────────────────


def success(t: str) -> str:
    return active_theme().success(t)


def error(t: str) -> str:
    return active_theme().error(t)


def warning(t: str) -> str:
    return active_theme().warning(t)
