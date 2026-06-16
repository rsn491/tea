from __future__ import annotations

from ..utils import _c, _rgb
from .theme import Theme


class LightTheme(Theme):
    """Green-tea palette tuned for light terminals.

    Deeper, more saturated swatches than ``DefaultTheme`` so text stays
    legible against a white background.
    """

    DEEP_JADE = (21, 115, 75)  # #15734B — accent / spinners (deep jade)
    FOREST = (28, 92, 60)  # #1C5C3C — bold-light accent (forest)
    PINE_GREEN = (24, 121, 72)  # #187948 — success (vivid pine)
    BRICK = (150, 60, 36)  # #963C24 — error / alerts (deep brick)
    OCHRE = (150, 100, 15)  # #96640F — warning (dark ochre)

    @classmethod
    def primary(cls, t: str) -> str:
        return _c(_rgb(*cls.DEEP_JADE), t)

    @classmethod
    def primary_light(cls, t: str) -> str:
        return _c(_rgb(*cls.FOREST), t)

    @classmethod
    def success(cls, t: str) -> str:
        return _c(_rgb(*cls.PINE_GREEN), t)

    @classmethod
    def error(cls, t: str) -> str:
        return _c(_rgb(*cls.BRICK), t)

    @classmethod
    def warning(cls, t: str) -> str:
        return _c(_rgb(*cls.OCHRE), t)
