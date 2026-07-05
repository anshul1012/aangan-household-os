"""Expense parsing: prompt builders for single messages and clarification threads."""

import datetime
import textwrap

from aangan.data.models import ExpenseCategory

_CATEGORIES = ", ".join(c.value for c in ExpenseCategory)

__all__ = ["build_expense_parse_prompt", "build_thread_parse_prompt"]


def _shared_field_rules(sender: str, today: datetime.date) -> str:
    return textwrap.dedent(f"""
        ## Context
        Today's date: {today.isoformat()}
        Message sender (default payer): {sender}

        ## Categories (pick exactly one, or return "none fit")
        {_CATEGORIES}

        ## Rules
        - amount: the numeric value of the expense. Negative for reimbursements/returns
          ("got back", "refund", "reimbursed", "returned"). If the amount is truly
          absent or ambiguous, return null — never guess a number.
        - category: must be one of the listed values exactly, or "none fit".
        - payer_person: who fronted the money. Default to "{sender}" unless the message
          names someone else (e.g. "aditi paid…" → "Aditi").
        - occurred_on: the financial date as YYYY-MM-DD. Resolve any relative language
          ("yesterday", "last Monday") using today = {today.isoformat()}.
          Default to today if no date is mentioned.
        - tags: list any specific vendor or app names mentioned
          (e.g. "Swiggy", "Blinkit", "Instamart", "Zepto", "Amazon"). Null if none.
    """).strip()


def build_expense_parse_prompt(message: str, sender: str, today: datetime.date) -> str:
    shared = _shared_field_rules(sender, today)
    return textwrap.dedent(f"""
        You are an expense-entry parser for a shared household ledger.
        Extract the fields below from the message and return them as JSON.
        Do not add explanation or any text outside the JSON.

        {shared}
        - confidence: your certainty across all fields. Return exactly one of: "high", "mid", "low".
          high = amount AND category both certain, AND date, payer, and tags (if any) are all
                 confidently resolved — nothing guessed or defaulted.
          mid  = amount AND category both confidently extracted, but at least one of date, payer,
                 or tags is inferred, defaulted, or ambiguous.
          low  = amount OR category cannot be confidently extracted — this takes priority over
                 every other field. If either is uncertain, return "low" even if everything else is clear.
        - clarification_question: null if confidence is "high".
          For "mid": state the assumed/defaulted values plainly and ask for a single-reply
          confirm-or-correct, e.g. "Logged as Help/Services, paid by you, dated today — right?
          Reply to fix anything, or just say 'yep'." Surface every field that was guessed or
          defaulted, not just one — the user should be able to fix everything in one reply.
          For "low": ask a short, specific question targeting the single most uncertain field
          (amount or category) — nothing has been saved yet, so keep it narrow and simple.
          Keep "mid" under 25 words; keep "low" under 15 words.

        ## Message
        {message}
    """).strip()


def build_thread_parse_prompt(
    thread_lines: list[tuple[str, str]],
    sender: str,
    today: datetime.date,
) -> str:
    shared = _shared_field_rules(sender, today)
    conversation = "\n".join(f"[{author}]: {content}" for author, content in thread_lines)
    return textwrap.dedent(f"""
        You are an expense-entry parser for a shared household ledger.
        A clarification thread was opened because the original message was ambiguous.
        Use the full conversation below to extract the expense fields and return them as JSON.
        Do not add explanation or any text outside the JSON.

        {shared}
        - confidence: your certainty across all fields. Return exactly one of: "high", "mid", "low".
          high = amount, category, date, payer, and tags are all resolved clearly from the conversation.
          mid  = amount and category are both clear, but at least one other field is still ambiguous.
          low  = amount or category is still missing or unclear.
        - clarification_question: null if confidence is "high".
          For "mid": state the assumed/defaulted values plainly and ask for a single-reply
          confirm-or-correct — surface every field that was guessed or defaulted, not just one,
          so the user can fix everything in one reply.
          For "low": ask a short, specific question targeting the single most uncertain field
          (amount or category) — nothing has been saved yet, so keep it narrow and simple.
          Keep "mid" under 25 words; keep "low" under 15 words.

        ## Conversation
        {conversation}
    """).strip()
