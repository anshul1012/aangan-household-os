"""Tests for the read-only query boundary (aangan/data/db.run_read_query).

The pure validation test needs no DB. The rest are integration tests against a
real Postgres: set TEST_DATABASE_URL (or POSTGRES_USER/PASSWORD/DB, host defaults
to localhost). When no DB is reachable they skip rather than fail, so `pytest`
stays green on a bare host; run them for real with a published Postgres port.
"""

import datetime
import os
from decimal import Decimal

import asyncpg
import pytest
import pytest_asyncio

from aangan.config.config import Config
from aangan.data import db
from aangan.data.db import QueryResultTooLarge, _validate_select_only, run_read_query
from aangan.data.models import Expense, ExpenseCategory, ExpenseStatus, MessageSource


# --- Pure validation (no DB) ---------------------------------------------


@pytest.mark.parametrize("bad", ["delete from expenses", "update expenses set amount=0", "  ", "insert into x values (1)"])
def test_validation_rejects_non_select(bad):
    with pytest.raises(ValueError):
        _validate_select_only(bad)


@pytest.mark.parametrize("ok", ["select 1", "  SELECT amount FROM expenses ;", "with c as (select 1) select * from c"])
def test_validation_allows_select_and_with(ok):
    _validate_select_only(ok)  # must not raise


def test_validation_rejects_statement_stacking():
    with pytest.raises(ValueError):
        _validate_select_only("select 1; drop table expenses")


# --- Integration (real Postgres) -----------------------------------------


def _test_dsn() -> str | None:
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url
    user, pw, name = (os.environ.get(k) for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"))
    host = os.environ.get("POSTGRES_HOST", "localhost")
    if user and name:
        return f"postgresql://{user}:{pw or ''}@{host}/{name}"
    return None


@pytest_asyncio.fixture
async def ready_db():
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("no test database configured (set TEST_DATABASE_URL or POSTGRES_*)")
    try:
        conn = await asyncpg.connect(dsn)
        await conn.close()
    except Exception as e:  # pragma: no cover - environmental
        pytest.skip(f"test database unreachable: {e}")

    config = Config(bot_token="x", gemini_api_key="x", database_url=dsn, allowed_channel_ids=frozenset({1}))
    await db.init_db(config)
    try:
        yield
    finally:
        await db.close_db()


async def _seed(raw_text: str = "readonly-test-seed") -> int:
    return await db.upsert_expense(
        Expense(
            amount=Decimal("100.00"),
            category=ExpenseCategory.GROCERIES.value,
            payer_person="Tester",
            raw_text=raw_text,
            occurred_on=datetime.date(2026, 1, 1),
            source=MessageSource.TEXT,
            status=ExpenseStatus.CONFIRMED,
        )
    )


async def test_select_returns_typed_rows(ready_db):
    await _seed("readonly-select-seed")
    rows = await run_read_query("SELECT amount, category FROM expenses WHERE raw_text = 'readonly-select-seed'")
    assert rows
    assert rows[0]["amount"] == Decimal("100.00")
    assert rows[0]["category"] == ExpenseCategory.GROCERIES.value


async def test_readonly_transaction_blocks_writes(ready_db):
    # A data-modifying CTE passes SELECT/WITH validation but must be refused by
    # the read-only transaction — this exercises the real safety boundary.
    await _seed("readonly-write-guard")
    with pytest.raises(asyncpg.exceptions.ReadOnlySQLTransactionError):
        await run_read_query(
            "WITH d AS (DELETE FROM expenses WHERE raw_text = 'readonly-write-guard' RETURNING id) SELECT id FROM d"
        )
    # And nothing was actually deleted.
    survived = await run_read_query("SELECT count(*) AS n FROM expenses WHERE raw_text = 'readonly-write-guard'")
    assert survived[0]["n"] >= 1


async def test_statement_timeout(ready_db, monkeypatch):
    monkeypatch.setattr(db, "_STATEMENT_TIMEOUT_MS", 100)
    with pytest.raises(asyncpg.exceptions.QueryCanceledError):
        await run_read_query("SELECT pg_sleep(1)")


async def test_row_cap_enforced(ready_db, monkeypatch):
    monkeypatch.setattr(db, "_ROW_CAP", 2)
    with pytest.raises(QueryResultTooLarge):
        await run_read_query("SELECT generate_series(1, 5)")
