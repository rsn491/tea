from __future__ import annotations

import abc


class Theme(abc.ABC):
    """Abstract base class for tea color themes.

    Subclass and implement all abstract classmethods to define a custom palette.
    """

    @classmethod
    @abc.abstractmethod
    def primary(cls, t: str) -> str:
        """Main accent color — spinners, test names, and decorative elements."""

    @classmethod
    @abc.abstractmethod
    def primary_light(cls, t: str) -> str:
        """Lighter accent — used for bold highlights such as the banner title."""

    @classmethod
    @abc.abstractmethod
    def success(cls, t: str) -> str:
        """Success state color — used for pass indicators and positive outcomes."""

    @classmethod
    @abc.abstractmethod
    def error(cls, t: str) -> str:
        """Error state color — used for failure indicators and alerts."""

    @classmethod
    @abc.abstractmethod
    def warning(cls, t: str) -> str:
        """Warning state color — used for partial results and cautions."""
