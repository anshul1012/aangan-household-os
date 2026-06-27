"""Database connection lifecycle and migration runner.

All DB access goes through this module ("queries in, typed results out").
Only connection management and migrations live here for now; query functions
are added as features need them.
"""

import logging
from pathlib import Path

import asyncpg

from aangan.config.config import Config
from aangan.data.models import Expense

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "db" / "migrations"


async def init_db(config: Config) -> None:
    global _pool
    dsn = (
        f"postgresql://{config.db_user}:{config.db_password}"
        f"@{config.db_host}/{config.db_name}"
    )
    _pool = await asyncpg.create_pool(dsn=dsn)
    logger.info("Database pool ready (host=%s db=%s)", config.db_host, config.db_name)
    await _run_migrations(_pool)


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised; call init_db() first.")
    return _pool


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed.")


async def insert_expense(expense: Expense) -> int:
    """Insert one expense row and return its generated id."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO expenses
                (amount, currency, category, tags, payer_person, payer_account,
                 occurred_on, raw_text, source, confidence, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            RETURNING id
            """,
            expense.amount, expense.currency, expense.category,
            expense.tags, expense.payer_person, expense.payer_account,
            expense.occurred_on, expense.raw_text, expense.source,
            expense.confidence, expense.status,
        )
        return row["id"]


async def _run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename   TEXT        PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        applied = {
            row["filename"]
            for row in await conn.fetch("SELECT filename FROM schema_migrations")
        }

        for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                logger.debug("Migration already applied, skipping: %s", path.name)
                continue
            logger.info("Applying migration: %s", path.name)
            async with conn.transaction():
                await conn.execute(path.read_text())
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)", path.name
                )
            logger.info("Migration applied: %s", path.name)
