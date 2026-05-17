from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelConfig:
    model: str
    api_key_env: str | None = None  # name of host env var to forward into container
    base_url: str | None = None  # OpenAI-compatible endpoint for local/custom providers
