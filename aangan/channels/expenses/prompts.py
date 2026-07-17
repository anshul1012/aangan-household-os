"""Expense parsing: prompt builders for single messages and clarification threads."""

import datetime
import textwrap

from aangan.data.models import ExpenseCategory

_CATEGORIES = ", ".join(c.value for c in ExpenseCategory)

__all__ = ["build_intent_prompt", "build_expense_parse_prompt", "build_thread_parse_prompt"]


def build_intent_prompt(message: str) -> str:
    return textwrap.dedent(f"""
        You are an expert at understanding the intent of user messages sent in a
        shared household's expense-tracking group. Classify the message into exactly
        one intent:

        - "expense_logging": the message records money spent or returned — an expense,
          payment, purchase, or reimbursement/refund to be logged.
        - "expense_query": the message asks a question about *past* spending — a total,
          breakdown, trend, ranking, or any insight about already-logged expenses.

        Safety rule: if the message plausibly records an expense, or is ambiguous,
        choose "expense_logging". Only choose "expense_query" when it is clearly asking
        about or for past-spend information.

        Examples:
        - "1800 groceries" -> expense_logging
        - "paid maid 4000" -> expense_logging
        - "got back 2000 from the clothes" -> expense_logging
        - "aditi paid 2000 medicines axis" -> expense_logging
        - "how much did we spend on groceries last week?" -> expense_query
        - "top spends this month" -> expense_query
        - "show me the dining trend" -> expense_query
        - "what's our total on Swiggy in June?" -> expense_query

        Return JSON with the intent and a short reason.

        ## Message
        {message}
    """).strip()


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
          mid  = amount is confidently extracted, but category is "none fit" / ambiguous,
                 and/or at least one of date, payer, or tags is inferred, defaulted, or ambiguous.
          low  = amount cannot be confidently extracted — this takes priority over every other
                 field. If the amount is uncertain, return "low" even if everything else is clear.
        - clarification_question: null if confidence is "high".
          For "mid" where category is ambiguous or "none fit": name 2-3 candidate categories from
          the list above and ask which fits, e.g. "Logged as Misc for now — is this Shopping or
          Personal Care?" For other "mid" cases: state the assumed/defaulted values plainly and
          ask for a single-reply confirm-or-correct, e.g. "Logged as Help/Services, paid by you,
          dated today — right? Reply to fix anything, or just say 'yep'." Surface every field that
          was guessed or defaulted, not just one — the user should be able to fix everything in
          one reply.
          For "low": ask a short, specific question targeting the amount — nothing has been saved
          yet, so keep it narrow and simple.
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
          mid  = amount is clear, but category is still "none fit" / ambiguous, and/or at least
                 one other field is still ambiguous.
          low  = amount is still missing or unclear.
        - clarification_question: null if confidence is "high".
          For "mid" where category is still ambiguous or "none fit": name 2-3 candidate categories
          from the list above and ask which fits. For other "mid" cases: state the assumed/defaulted
          values plainly and ask for a single-reply confirm-or-correct — surface every field that
          was guessed or defaulted, not just one, so the user can fix everything in one reply.
          For "low": ask a short, specific question targeting the amount — nothing has been saved
          yet, so keep it narrow and simple.
          Keep "mid" under 25 words; keep "low" under 15 words.

        ## Conversation
        {conversation}
    """).strip()
