"""Unit tests for the insights table formatter (pure, no DB/LLM)."""

import datetime
from decimal import Decimal

from aangan.insights.tables import format_table


def test_empty_rows_returns_empty():
    assert format_table([], []) == ""


def test_money_and_date_formatting():
    rows = [
        {"category": "Groceries", "total": Decimal("2500.00")},
        {"category": "Dining", "total": Decimal("950.00")},
    ]
    out = format_table(rows, ["category", "total"])
    assert out.startswith("```") and out.endswith("```")
    assert "₹2,500" in out
    assert "₹950" in out
    assert "category" in out and "total" in out


def test_none_renders_as_dash():
    out = format_table([{"day": datetime.date(2026, 7, 8), "note": None}], ["day", "note"])
    assert "2026-07-08" in out
    assert "—" in out


def test_row_cap_truncates():
    rows = [{"n": i} for i in range(30)]
    out = format_table(rows, ["n"])
    assert "+10 more rows" in out


def test_non_money_numeric_string_not_rupee():
    # A numeric string in a non-money column must not gain a ₹ prefix.
    out = format_table([{"account_id": "12345"}], ["account_id"])
    assert "₹" not in out
    assert "12345" in out
