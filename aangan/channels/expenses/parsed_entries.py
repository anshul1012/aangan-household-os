"""Pydantic schema for the LLM-parsed expense entry."""

from pydantic import BaseModel

__all__ = ["ParsedEntry"]

class ParsedEntry(BaseModel):
    amount: float | None   # None if genuinely unparseable — caller must gate on this
    category: str          # one of the 14 ExpenseCategory values, or "none fit"
    payer_person: str      # defaults to sender; overridden if another name is mentioned
    occurred_on: str       # resolved ISO date YYYY-MM-DD
    tags: list[str] | None # vendor/app names e.g. ["Swiggy"], ["Blinkit"]; null if none
    confidence: float      # 0.0–1.0 across all fields
