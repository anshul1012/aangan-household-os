"""Configuration loaded from the environment.

In local dev, values come from a gitignored ``.env`` (see ``main.py``).
In production the container injects them as real env vars.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    bot_token: str
    gemini_api_key: str
    db_user: str = ""
    db_password: str = ""
    db_name: str = ""
    db_host: str = "db"   # matches the compose service name; override for local non-Docker dev
    gemini_model: str = "gemini-2.0-flash"  # override via GEMINI_MODEL; update when model is deprecated
    database_url: str | None = None  # prod (Supabase): takes priority over db_user/db_password/db_name
    allowed_channel_ids: frozenset[int] = field(default_factory=frozenset)  # this bot instance only reacts here


def load_config() -> Config:
    def require(key: str) -> str:
        val = os.environ.get(key)
        if not val:
            raise RuntimeError(f"{key} is not set. Copy .env.example to .env and fill it in.")
        return val

    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        db_user = db_password = db_name = ""
    else:
        db_user = require("POSTGRES_USER")
        db_password = require("POSTGRES_PASSWORD")
        db_name = require("POSTGRES_DB")

    raw_channel_ids = require("ALLOWED_CHANNEL_IDS")
    try:
        allowed_channel_ids = frozenset(int(part.strip()) for part in raw_channel_ids.split(",") if part.strip())
    except ValueError as e:
        raise RuntimeError(f"ALLOWED_CHANNEL_IDS must be a comma-separated list of channel IDs, got: {raw_channel_ids!r}") from e
    if not allowed_channel_ids:
        raise RuntimeError("ALLOWED_CHANNEL_IDS is set but contains no channel IDs.")

    return Config(
        bot_token=require("BOT_TOKEN"),
        gemini_api_key=require("GEMINI_API_KEY"),
        db_user=db_user,
        db_password=db_password,
        db_name=db_name,
        db_host=os.environ.get("POSTGRES_HOST", "db"),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        database_url=database_url,
        allowed_channel_ids=allowed_channel_ids,
    )
