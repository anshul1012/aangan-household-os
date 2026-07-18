"""Expenses channel handler.

Every message is first classified by a semantic router (logging vs querying).
Queries route to the insights stub (the agentic pipeline isn't built yet); an
ambiguous or failed classification degrades to logging — a dropped expense is the
worst outcome. The rest of this module is the logging path.

Parses each logged message with Gemini. Amount is the only field that can ever block
persistence — if it's null/unparseable, nothing is saved until a thread reply
resolves it. Category is never blocking: an unrecognized value (the model's
"none fit", or any hallucinated ad-hoc string) is defaulted to Misc so invalid
category strings never reach the DB, and a targeted clarification is asked
instead. HIGH confidence with a valid category persists and reacts silently;
anything else (MEDIUM, or a category default) persists a best-guess row
immediately and opens a thread to refine it. Thread replies re-parse the full
conversation and upsert the same row (keyed by the originating message id) as
confidence improves, until it reaches HIGH or the clarification round cap.
"""

import datetime
import logging
from decimal import Decimal
from zoneinfo import ZoneInfo

import discord

from aangan.channels.base import BaseHandler
from aangan.channels.expenses.parsed_entries import (
    ConfidenceLevel,
    IntentClassification,
    MessageIntent,
    ParsedExpense,
)
from aangan.channels.expenses.prompts import (
    build_expense_parse_prompt,
    build_intent_prompt,
    build_thread_parse_prompt,
)
from aangan.data.db import upsert_expense
from aangan.data.models import Expense, ExpenseCategory, ExpenseStatus, MessageSource
from aangan.insights.agent import answer as insights_answer
from aangan.llm import generate_json

logger = logging.getLogger(__name__)

_THREAD_LIMIT = 5              # clarification rounds before giving up and closing the thread
_THREAD_HISTORY_FETCH_LIMIT = 50  # Discord history page size; independent of the round cap above

_VALID_CATEGORIES = {c.value for c in ExpenseCategory}
_CATEGORY_LIST = ", ".join(c.value for c in ExpenseCategory)

# The household is IST-based; "today" must resolve to the household's local
# calendar date regardless of the container's own timezone (Docker defaults to
# UTC), since occurred_on/"yesterday" resolution and all reports key off it.
_HOUSEHOLD_TZ = ZoneInfo("Asia/Kolkata")


def _today() -> datetime.date:
    return datetime.datetime.now(_HOUSEHOLD_TZ).date()


async def _classify_intent(text: str) -> MessageIntent:
    """Route a message to logging vs querying. Any failure degrades to logging —
    the safe direction, since a dropped expense is the worst outcome."""
    try:
        result = await generate_json(build_intent_prompt(text), IntentClassification)
        logger.info("Intent=%s (%s)", result.intent, result.reason)
        return result.intent
    except Exception:
        logger.exception("Intent classification failed; defaulting to expense logging")
        return MessageIntent.EXPENSE_LOGGING


async def _resolve(message: discord.Message, *emojis: str) -> None:
    """Clear the ⏳ receipt ack and stamp the outcome reaction(s)."""
    try:
        await message.remove_reaction("⏳", message.guild.me)
    except discord.HTTPException:
        pass  # ack may not have landed; the outcome reaction still tells the story
    for emoji in emojis:
        await message.add_reaction(emoji)


def _normalize_category(category: str) -> tuple[str, bool]:
    """Returns (category, was_defaulted). Defaults anything outside the fixed
    enum — the model's "none fit", or any hallucinated ad-hoc value — to Misc
    so an invalid category string never reaches the DB."""
    if category in _VALID_CATEGORIES:
        return category, False
    return ExpenseCategory.MISC.value, True


def _category_clarification_question() -> str:
    return f"Logged as {ExpenseCategory.MISC.value} for now — which category fits better: {_CATEGORY_LIST}?"


def _to_expense(
    parsed: ParsedExpense, raw_text: str, source_message_id: int, category: str, needs_followup: bool
) -> Expense:
    return Expense(
        amount=Decimal(str(parsed.amount)),
        category=category,
        payer_person=parsed.payer_person,
        raw_text=raw_text,
        occurred_on=datetime.date.fromisoformat(parsed.occurred_on),
        tags=parsed.tags,
        source=MessageSource.TEXT,
        confidence=parsed.confidence,
        status=ExpenseStatus.PENDING if needs_followup else ExpenseStatus.CONFIRMED,
        source_message_id=source_message_id,
    )


def _summary_line(parsed: ParsedExpense, category: str) -> str:
    parts = [f"₹{parsed.amount:g}", category, parsed.payer_person, parsed.occurred_on]
    if parsed.tags:
        parts.append(", ".join(parsed.tags))
    return " · ".join(parts)

async def _thread_history(thread: discord.Thread) -> tuple[list[tuple[str, str]], int]:
    # The starter message (original expense text) is not in thread history —
    # Discord sets thread.id == starter message id, so fetch it from the parent channel.

    starter = await thread.parent.fetch_message(thread.id)

    thread_messages = [
        m async for m in thread.history(oldest_first=True, limit=_THREAD_HISTORY_FETCH_LIMIT)
        if m.content.strip()  # skip empty system messages (thread-created events)
    ]

    thread_lines = (
            [(starter.author.display_name, starter.content)]
            + [(m.author.display_name, m.content) for m in thread_messages]
    )
    # Number of clarification rounds asked so far — one bot message per round.
    # Used to cap follow-ups at _THREAD_LIMIT regardless of raw message count.
    rounds_asked = sum(1 for m in thread_messages if m.author.bot)
    return thread_lines, rounds_asked

async def _persist(
    parsed: ParsedExpense, raw_text: str, source_message_id: int, category: str, needs_followup: bool
) -> int:
    expense = _to_expense(parsed, raw_text, source_message_id, category, needs_followup)
    expense_id = await upsert_expense(expense)
    logger.info("Saved expense id=%s: %s", expense_id, expense)
    return expense_id


class ExpensesHandler(BaseHandler):
    CHANNEL_NAME = "expenses"

    async def handle_message(self, message: discord.Message) -> None:
        await message.add_reaction("⏳")  # ack on receipt; resolved once routed + handled
        intent = await _classify_intent(message.content)
        if intent == MessageIntent.EXPENSE_QUERY:
            await self._handle_expense_query(message)
        else:
            await self._handle_expense_log(message)

    async def _handle_expense_query(self, message: discord.Message) -> None:
        # Agentic insights (spec §8.1): the LLM authors read-only SQL, Postgres does the
        # math, and narrates the answer. answer() never raises — a query error degrades to
        # a graceful message, never a crash or a dropped entry.
        narration = await insights_answer(message.content, _today())
        await _resolve(message, "📊")
        await message.reply(narration)

    async def _handle_expense_log(self, message: discord.Message) -> None:
        prompt = build_expense_parse_prompt(
            message=message.content,
            sender=message.author.display_name,
            today=_today(),
        )
        logger.debug("Prompt: %s", prompt)
        parsed = await generate_json(prompt, ParsedExpense)

        if parsed.amount is None:
            logger.info(
                "Confidence=%s — clarification needed: %s",
                parsed.confidence,
                parsed.clarification_question,
            )
            await _resolve(message, "🤔")
            thread = await message.create_thread(name=message.content[:100])
            await thread.send(f"{message.author.mention} {parsed.clarification_question}")
            return

        category, category_was_defaulted = _normalize_category(parsed.category)
        needs_followup = category_was_defaulted or parsed.confidence != ConfidenceLevel.HIGH
        await _persist(
            parsed, message.content, source_message_id=message.id,
            category=category, needs_followup=needs_followup,
        )

        if not needs_followup:
            await _resolve(message, "✅")
        else:  # persisted, but still asking to refine the category or other soft fields
            await _resolve(message, "✅", "🤔")
            thread = await message.create_thread(name=message.content[:100])
            question = _category_clarification_question() if category_was_defaulted else parsed.clarification_question
            await thread.send(f"{message.author.mention} {question}")

    async def handle_thread(self, message: discord.Message) -> None:
        thread = message.channel
        if not thread or not isinstance(thread, discord.Thread):
            return
        if thread.locked:
            return  # already finalized; ignore replies to a reopened thread

        thread_history, rounds_asked = await _thread_history(thread)
        for author, content in thread_history:
            logger.info("  %s: %s", author, content)
        raw_text = "\n".join(f"[{author}]: {content}" for author, content in thread_history)

        prompt = build_thread_parse_prompt(
            thread_lines=thread_history,
            sender=message.author.display_name,
            today=_today(),
        )
        logger.debug("Prompt: %s", prompt)
        parsed = await generate_json(prompt, ParsedExpense)
        at_limit = rounds_asked >= _THREAD_LIMIT

        if parsed.amount is None:
            logger.info(
                "Still unclear after thread (confidence=%s): %s",
                parsed.confidence,
                parsed.clarification_question,
            )
            if at_limit:
                await thread.send(
                    f"{message.author.mention} Still couldn't figure this one out — please log it again."
                )
                await thread.edit(locked=True, archived=True)
            else:
                await thread.send(f"{message.author.mention} {parsed.clarification_question}")
            return

        category, category_was_defaulted = _normalize_category(parsed.category)
        needs_followup = category_was_defaulted or parsed.confidence != ConfidenceLevel.HIGH
        await _persist(
            parsed, raw_text, source_message_id=thread.id,
            category=category, needs_followup=needs_followup,
        )

        if not needs_followup:
            await thread.send("✅ Got it, logged!")
            await thread.edit(locked=True, archived=True)
        else:
            if at_limit:
                await thread.send(
                    f"{message.author.mention} Saved with best guess — "
                    f"{_summary_line(parsed, category)} — closing this thread."
                )
                await thread.edit(locked=True, archived=True)
            else:
                question = _category_clarification_question() if category_was_defaulted else parsed.clarification_question
                await thread.send(f"{message.author.mention} {question}")
