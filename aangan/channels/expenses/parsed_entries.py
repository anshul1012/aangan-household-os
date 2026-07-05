"""Pydantic schema for the LLM-parsed expense entry."""

from enum import StrEnum

from pydantic import BaseModel

__all__ = ["ConfidenceLevel", "ParsedExpense"]


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MID = "mid"
    LOW = "low"


class ParsedExpense(BaseModel):
    amount: float | None        # None if genuinely unparseable — caller must gate on this
    category: str               # one of the 14 ExpenseCategory values, or "none fit"
    payer_person: str           # defaults to sender; overridden if another name is mentioned
    occurred_on: str            # resolved ISO date YYYY-MM-DD
    tags: list[str] | None      # vendor/app names e.g. ["Swiggy"], ["Blinkit"]; null if none
    confidence: ConfidenceLevel             # high / mid / low across all fields
    clarification_question: str | None     # null for HIGH; targeted question for MID / LOW
