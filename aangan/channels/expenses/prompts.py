"""Expense parsing: Pydantic output schema and prompt builder."""

import datetime
import textwrap

from aangan.data.models import ExpenseCategory

_CATEGORIES = ", ".join(c.value for c in ExpenseCategory)

__all__ = ["build_expense_parse_prompt"]


def build_expense_parse_prompt(message: str, sender: str, today: datetime.date) -> str:
    return textwrap.dedent(f"""
        You are an expense-entry parser for a shared household ledger.
        Extract the fields below from the message and return them as JSON.
        Do not add explanation or any text outside the JSON.

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
        - confidence: your certainty across all fields. Return exactly one of: "high", "mid", "low".
          high = amount clear, category certain, date unambiguous, payer obvious, tags (if any) clearly identified.
          mid  = amount clear but one field is inferred or ambiguous (category guessed, date defaulted
                 without being stated, payer assumed as sender, tags uncertain).
          low  = amount missing or unclear, or two or more fields are uncertain or unresolvable.
        - clarification_question: null if confidence is "high".
          For "mid" or "low", return a short, specific question targeting the single most
          uncertain field. Ask about one thing only — do not ask the user to repeat the whole message.
          Examples:
            amount unclear   → "How much was this?"
            category unclear → "What's this for — Housing, Transport, or something else?"
            payer unclear    → "Who paid for this?"
          Keep it conversational, under 15 words.

        ## Message
        {message}
    """).strip()
