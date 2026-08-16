"""Tests for the weekly report's top-5-expenses addition.

The formatting test needs no DB. fetch_top_expenses is an integration test
against a real Postgres: set TEST_DATABASE_URL (or POSTGRES_USER/PASSWORD/DB,
host defaults to localhost). Skips rather than fails when no DB is reachable,
matching tests/test_readonly.py's pattern.
"""

import datetime
import os
from decimal import Decimal

import asyncpg
import pytest
import pytest_asyncio

from aangan.config.config import Config
from aangan.data import db
from aangan.data.db import fetch_top_expenses
from aangan.data.models import Expense, ExpenseCategory, ExpenseStatus, MessageSource, TopExpense
from aangan.insights.weekly_report import _fmt_top_expense


# --- Pure formatting (no DB) -----------------------------------------------


def test_fmt_top_expense_renders_amount_category_text_and_date():
    e = TopExpense(
        amount=Decimal("4200"),
        category=ExpenseCategory.SHOPPING.value,
        raw_text="zara jacket on amex",
        occurred_on=datetime.date(2026, 8, 12),
    )
    assert _fmt_top_expense(e) == "₹4,200  Shopping — zara jacket on amex (12 Aug)"


def test_fmt_top_expense_truncates_long_raw_text():
    e = TopExpense(
        amount=Decimal("100"),
        category=ExpenseCategory.MISC.value,
        raw_text="x" * 100,
        occurred_on=datetime.date(2026, 8, 12),
    )
    rendered = _fmt_top_expense(e)
    assert "..." in rendered
    assert len(rendered) < 120


# --- Integration (real Postgres) -------------------------------------------


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


async def _seed(amount: Decimal, raw_text: str, occurred_on: datetime.date) -> int:
    return await db.upsert_expense(
        Expense(
            amount=amount,
            category=ExpenseCategory.SHOPPING.value,
            payer_person="Tester",
            raw_text=raw_text,
            occurred_on=occurred_on,
            source=MessageSource.TEXT,
            status=ExpenseStatus.CONFIRMED,
        )
    )


async def test_fetch_top_expenses_excludes_reimbursements_and_orders_desc(ready_db):
    day = datetime.date(2026, 2, 10)
    await _seed(Decimal("500"), "top-expenses-small", day)
    await _seed(Decimal("4200"), "top-expenses-large", day)
    await _seed(Decimal("-1000"), "top-expenses-reimbursement", day)

    results = await fetch_top_expenses(day, day, limit=5)
    texts = [r.raw_text for r in results]

    assert "top-expenses-reimbursement" not in texts
    large_idx = texts.index("top-expenses-large")
    small_idx = texts.index("top-expenses-small")
    assert large_idx < small_idx  # amount-descending


async def test_fetch_top_expenses_respects_limit(ready_db):
    day = datetime.date(2026, 2, 11)
    for i in range(7):
        await _seed(Decimal(100 + i), f"top-expenses-limit-{i}", day)

    results = await fetch_top_expenses(day, day, limit=5)
    assert len(results) <= 5
