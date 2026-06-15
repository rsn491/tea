from __future__ import annotations

import abc
import os

_NO_SPINNER = os.environ.get("NO_SPINNER") is not None


class Theme(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def primary(cls, t: str) -> str: ...

    @classmethod
    @abc.abstractmethod
    def primary_light(cls, t: str) -> str: ...

    @classmethod
    @abc.abstractmethod
    def success(cls, t: str) -> str: ...

    @classmethod
    @abc.abstractmethod
    def error(cls, t: str) -> str: ...
