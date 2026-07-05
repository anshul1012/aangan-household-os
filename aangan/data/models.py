"""Python-side data models mirroring the database schema.

No ORM — the data-access layer (db.py) uses explicit SQL. These dataclasses
are the typed currency passed between db.py and the rest of the application.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class ExpenseCategory(StrEnum):
    """Fixed enum enforced in Python. Stored as TEXT in the DB so new values
    can be added here without a schema migration."""
    HOUSING = "Housing"
    UTILITIES = "Utilities"
    GROCERIES = "Groceries"
    DINING = "Dining"
    TRANSPORT = "Transport"
    HEALTH = "Health/Fitness"
    MEDICAL = "Medical"
    HELP_SERVICES = "Help/Services"
    SHOPPING = "Shopping"
    SUBSCRIPTIONS = "Subscriptions"
    ENTERTAINMENT = "Entertainment"
    TRAVEL = "Travel"
    PERSONAL_CARE = "Personal Care"
    GIFTS_DONATIONS = "Gifts/Donations"
    MISC = "Misc"


class MessageSource(StrEnum):
    TEXT = "text"
    VOICE = "voice"


class ExpenseStatus(StrEnum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    AUTO = "auto"


@dataclass
class Expense:
    amount: Decimal
    category: str                          # one of ExpenseCategory; TEXT in DB
    payer_person: str
    raw_text: str
    occurred_on: datetime.date
    id: int | None = None
    currency: str = "INR"
    tags: list[str] | None = None          # optional drill-down e.g. ["Swiggy"]
    payer_account: str | None = None
    logged_at: datetime.datetime | None = None
    source: MessageSource = MessageSource.TEXT
    confidence: str | None = None          # one of ConfidenceLevel values; TEXT in DB
    status: ExpenseStatus = ExpenseStatus.PENDING
    source_message_id: int | None = None   # Discord message id that created/refines this row


@dataclass
class GlossaryEntry:
    raw_name: str                          # lowercased lookup key
    display_name: str
    category: str                          # one of ExpenseCategory
    id: int | None = None
    note: str | None = None
    updated_at: datetime.datetime | None = None


@dataclass
class KnownAccount:
    alias: str
    canonical_name: str
    id: int | None = None
    updated_at: datetime.datetime | None = None
