from __future__ import annotations

from ..utils import _c, _rgb
from .theme import Theme


class DefaultTheme(Theme):
    """Green-tea palette tuned for dark terminals (the default)."""

    PALE_JADE = (164, 194, 136)  # #A4C288 — base text (lightest sage)
    SENCHA = (74, 168, 120)  # #4AA878 — accent / success (vibrant jade)
    YUZU = (132, 104, 70)  # #846846 — error / alerts (warm brown)

    MUTED_SAGE = (130, 168, 126)  # #82A87E — muted sage (bold-light accent)
    AMBER = (216, 170, 90)  # #D8AA5A — warning (warm amber)

    @classmethod
    def primary(cls, t: str) -> str:
        return _c(_rgb(*cls.SENCHA), t)

    @classmethod
    def primary_light(cls, t: str) -> str:
        return _c(_rgb(*cls.MUTED_SAGE), t)

    @classmethod
    def success(cls, t: str) -> str:
        return _c(_rgb(*cls.PALE_JADE), t)

    @classmethod
    def error(cls, t: str) -> str:
        return _c(_rgb(*cls.YUZU), t)

    @classmethod
    def warning(cls, t: str) -> str:
        return _c(_rgb(*cls.AMBER), t)
