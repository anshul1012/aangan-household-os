"""Configuration loaded from the environment.

In local dev, values come from a gitignored ``.env`` (see ``main.py``).
In production the container injects them as real env vars.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    bot_token: str


def load_config() -> Config:
    token = os.environ.get("bot_token")
    if not token:
        raise RuntimeError(
            "bot_token is not set. Copy .env.example to .env and fill it in, "
            "or export bot_token in the environment."
        )
    return Config(bot_token=token)
