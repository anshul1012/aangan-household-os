"""Database connection lifecycle and migration runner.

All DB access goes through this module ("queries in, typed results out").
Only connection management and migrations live here for now; query functions
are added as features need them.
"""

import datetime
import logging
from pathlib import Path

import asyncpg

from aangan.config.config import Config
from aangan.data.models import CategoryTotal, Expense, TopExpense

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "db" / "migrations"


async def init_db(config: Config) -> None:
    global _pool
    dsn = config.database_url or (
        f"postgresql://{config.db_user}:{config.db_password}"
        f"@{config.db_host}/{config.db_name}"
    )
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=3)
    logger.info(
        "Database pool ready (%s)",
        "via DATABASE_URL" if config.database_url else f"host={config.db_host} db={config.db_name}",
    )
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


async def upsert_expense(expense: Expense) -> int:
    """Insert a new expense, or update the existing row sharing the same
    source_message_id (a thread reply refining an earlier MEDIUM-confidence
    guess). logged_at is deliberately excluded from the UPDATE SET list so it
    always reflects the original log time, not the latest refinement."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO expenses
                (amount, currency, category, tags, payer_person, payer_account,
                 occurred_on, raw_text, source, confidence, status, source_message_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            ON CONFLICT (source_message_id) WHERE source_message_id IS NOT NULL
            DO UPDATE SET
                amount = EXCLUDED.amount,
                category = EXCLUDED.category,
                tags = EXCLUDED.tags,
                payer_person = EXCLUDED.payer_person,
                payer_account = EXCLUDED.payer_account,
                occurred_on = EXCLUDED.occurred_on,
                raw_text = EXCLUDED.raw_text,
                confidence = EXCLUDED.confidence,
                status = EXCLUDED.status
            RETURNING id
            """,
            expense.amount, expense.currency, expense.category,
            expense.tags, expense.payer_person, expense.payer_account,
            expense.occurred_on, expense.raw_text, expense.source,
            expense.confidence, expense.status, expense.source_message_id,
        )
        return row["id"]


async def fetch_category_totals(
    period_start: datetime.date, period_end: datetime.date
) -> list[CategoryTotal]:
    """Net spend per category for occurred_on in [period_start, period_end],
    inclusive — net of reimbursements/returns (negative entries fold into
    SUM by construction, spec §8). A category with zero net spend across the
    period (e.g. fully reimbursed) is simply absent from the result, not a
    zero-valued row — GROUP BY only returns groups with >=1 matching row.
    Trusted, code-authored SQL — distinct from run_read_query below, which is
    reserved for untrusted LLM-authored SQL."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE occurred_on BETWEEN $1 AND $2
            GROUP BY category
            """,
            period_start, period_end,
        )
    return [CategoryTotal(category=r["category"], total=r["total"]) for r in rows]


async def fetch_top_expenses(
    period_start: datetime.date, period_end: datetime.date, limit: int = 5
) -> list[TopExpense]:
    """The `limit` largest individual positive expenses for occurred_on in
    [period_start, period_end], inclusive. Reimbursements/returns (amount <= 0)
    are excluded — this lists outflows, not net category totals (see
    fetch_category_totals for that). Trusted, code-authored SQL."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT amount, category, raw_text, occurred_on
            FROM expenses
            WHERE occurred_on BETWEEN $1 AND $2 AND amount > 0
            ORDER BY amount DESC
            LIMIT $3
            """,
            period_start, period_end, limit,
        )
    return [
        TopExpense(amount=r["amount"], category=r["category"], raw_text=r["raw_text"], occurred_on=r["occurred_on"])
        for r in rows
    ]


# --- Read path: untrusted, LLM-authored SQL -------------------------------
# Everything above is the trusted write path. run_read_query is the ONE place
# LLM-authored SQL executes (the V2 insights agent, spec §8.1). The safety
# boundary is the read-only transaction, not the caller: any write raises
# ReadOnlySQLTransactionError, so the worst case is a wrong number the user can
# sanity-check, never mutated state.

_STATEMENT_TIMEOUT_MS = 5000  # per-query cap; promote to Config later if needed
_ROW_CAP = 1000               # refuse to return unbounded result sets


class QueryResultTooLarge(Exception):
    """Raised when a read query returns more than _ROW_CAP rows — the caller
    should aggregate in SQL or add a LIMIT rather than pull the raw set."""


def _validate_select_only(sql: str) -> None:
    """Defense-in-depth so bad SQL fails with a clear message before hitting the
    DB. The read-only transaction is the real guard; this is not a security
    boundary on its own."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise ValueError("Empty SQL query.")
    if ";" in stripped:  # statement stacking (asyncpg's extended protocol also blocks this)
        raise ValueError("Multiple SQL statements are not allowed.")
    first = stripped.split(None, 1)[0].lower()
    if first not in ("select", "with"):
        raise ValueError(f"Only SELECT/WITH queries are allowed, got: {first!r}")


async def run_read_query(sql: str) -> list[dict]:
    """Execute untrusted, LLM-authored read-only SQL and return rows as dicts.

    Runs inside a READ ONLY transaction with a per-statement timeout; writes
    raise asyncpg.exceptions.ReadOnlySQLTransactionError. SET LOCAL is scoped to
    the transaction and reverts on commit, so the pooled connection is never
    left altered for a later write."""
    _validate_select_only(sql)
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            await conn.execute(f"SET LOCAL statement_timeout = {_STATEMENT_TIMEOUT_MS}")
            rows = await conn.fetch(sql)
    if len(rows) > _ROW_CAP:
        raise QueryResultTooLarge(
            f"Query returned more than {_ROW_CAP} rows; aggregate in SQL or add a LIMIT."
        )
    return [dict(r) for r in rows]


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
