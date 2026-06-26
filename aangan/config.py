"""Configuration loaded from the environment.

In local dev, values come from a gitignored ``.env`` (see ``main.py``).
In production the container injects them as real env vars.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_user: str
    db_password: str
    db_name: str
    db_host: str = "db"   # matches the compose service name; override for local non-Docker dev


def load_config() -> Config:
    def require(key: str) -> str:
        val = os.environ.get(key)
        if not val:
            raise RuntimeError(f"{key} is not set. Copy .env.example to .env and fill it in.")
        return val

    return Config(
        bot_token=require("bot_token"),
        db_user=require("POSTGRES_USER"),
        db_password=require("POSTGRES_PASSWORD"),
        db_name=require("POSTGRES_DB"),
        db_host=os.environ.get("POSTGRES_HOST", "db"),
    )
