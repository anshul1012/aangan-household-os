"""Render query rows as a fixed-width text table for Discord.

Discord has no native table; a fenced code block with aligned columns is the
reliable, mobile-friendly form. Money columns get ₹ + thousands separators. All
values come straight from the DB rows — no arithmetic here.
"""

import datetime
from decimal import Decimal, InvalidOperation

__all__ = ["format_table"]

_MAX_ROWS = 20


def _is_money(column: str, value) -> bool:
    if isinstance(value, Decimal):
        return True
    if isinstance(value, str):
        try:
            Decimal(value)
        except (InvalidOperation, ValueError):
            return False
        # Only treat numeric strings in money-ish columns as money.
        return any(k in column.lower() for k in ("amount", "total", "spend", "spent", "sum", "paid"))
    return False


def _fmt(column: str, value) -> str:
    if value is None:
        return "—"
    if _is_money(column, value):
        return f"₹{Decimal(str(value)):,.0f}"
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return str(value)


def format_table(rows: list[dict], columns: list[str] | None = None) -> str:
    """Return a fenced code block with the rows as an aligned table. Empty if no rows."""
    if not rows:
        return ""
    columns = columns or list(rows[0].keys())

    shown = rows[:_MAX_ROWS]
    cells = [[_fmt(c, r.get(c)) for c in columns] for r in shown]
    widths = [
        max(len(str(col)), *(len(row[i]) for row in cells)) if cells else len(str(col))
        for i, col in enumerate(columns)
    ]

    def line(values: list[str]) -> str:
        return "  ".join(v.ljust(widths[i]) for i, v in enumerate(values))

    out = [line([str(c) for c in columns]), line(["-" * w for w in widths])]
    out += [line(row) for row in cells]
    if len(rows) > _MAX_ROWS:
        out.append(f"… (+{len(rows) - _MAX_ROWS} more rows)")
    return "```\n" + "\n".join(out) + "\n```"
