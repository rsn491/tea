from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class JudgeResult:
    score: float
    rationale: str


class Judge(ABC):
    @abstractmethod
    def evaluate(self, content: str, prompt: str) -> JudgeResult: ...
