"""Expenses channel handler.

Parses each message with Gemini. HIGH confidence persists and reacts silently.
MEDIUM persists a best-guess row immediately and opens a thread to refine the
soft fields (tags/payer/date). LOW opens a thread without persisting anything
until amount and category are both resolved. Thread replies re-parse the full
conversation and upsert the same row (keyed by the originating message id) as
confidence improves, until it reaches HIGH or the clarification round cap.
"""

import datetime
import logging
from decimal import Decimal

import discord

from aangan.channels.base import BaseHandler
from aangan.channels.expenses.parsed_entries import ConfidenceLevel, ParsedExpense
from aangan.channels.expenses.prompts import build_expense_parse_prompt, build_thread_parse_prompt
from aangan.data.db import upsert_expense
from aangan.data.models import Expense, ExpenseStatus, MessageSource
from aangan.llm import generate_json

logger = logging.getLogger(__name__)

_THREAD_LIMIT = 5              # clarification rounds before giving up and closing the thread
_THREAD_HISTORY_FETCH_LIMIT = 50  # Discord history page size; independent of the round cap above


def _to_expense(parsed: ParsedExpense, raw_text: str, source_message_id: int) -> Expense:
    return Expense(
        amount=Decimal(str(parsed.amount)),
        category=parsed.category,
        payer_person=parsed.payer_person,
        raw_text=raw_text,
        occurred_on=datetime.date.fromisoformat(parsed.occurred_on),
        tags=parsed.tags,
        source=MessageSource.TEXT,
        confidence=parsed.confidence,
        status=ExpenseStatus.CONFIRMED if parsed.confidence == ConfidenceLevel.HIGH else ExpenseStatus.PENDING,
        source_message_id=source_message_id,
    )


def _summary_line(parsed: ParsedExpense) -> str:
    parts = [f"₹{parsed.amount:g}", parsed.category, parsed.payer_person, parsed.occurred_on]
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

async def _persist(parsed: ParsedExpense, raw_text: str, source_message_id: int) -> int:
    expense = _to_expense(parsed, raw_text, source_message_id)
    expense_id = await upsert_expense(expense)
    logger.info("Saved expense id=%s: %s", expense_id, expense)
    return expense_id


class ExpensesHandler(BaseHandler):
    CHANNEL_NAME = "expenses"

    async def handle_message(self, message: discord.Message) -> None:
        prompt = build_expense_parse_prompt(
            message=message.content,
            sender=message.author.display_name,
            today=datetime.date.today(),
        )
        logger.debug("Prompt: %s", prompt)
        parsed = await generate_json(prompt, ParsedExpense)

        if parsed.amount is None or parsed.confidence == ConfidenceLevel.LOW:
            logger.info(
                "Confidence=%s — clarification needed: %s",
                parsed.confidence,
                parsed.clarification_question,
            )
            await message.add_reaction("🤔")
            thread = await message.create_thread(name=message.content[:100])
            await thread.send(f"{message.author.mention} {parsed.clarification_question}")
            return

        await _persist(parsed, message.content, source_message_id=message.id)

        if parsed.confidence == ConfidenceLevel.HIGH:
            await message.add_reaction("✅")
        else:  # MEDIUM — persisted, but still asking to refine soft fields
            await message.add_reaction("✅")
            await message.add_reaction("🤔")
            thread = await message.create_thread(name=message.content[:100])
            await thread.send(f"{message.author.mention} {parsed.clarification_question}")

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
            today=datetime.date.today(),
        )
        logger.debug("Prompt: %s", prompt)
        parsed = await generate_json(prompt, ParsedExpense)
        at_limit = rounds_asked >= _THREAD_LIMIT

        if parsed.amount is None or parsed.confidence == ConfidenceLevel.LOW:
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

        await _persist(parsed, raw_text, source_message_id=thread.id)

        if parsed.confidence == ConfidenceLevel.HIGH:
            await thread.send("✅ Got it, logged!")
            await thread.edit(locked=True, archived=True)
        else:  # MEDIUM
            if at_limit:
                await thread.send(
                    f"{message.author.mention} Saved with best guess — "
                    f"{_summary_line(parsed)} — closing this thread."
                )
                await thread.edit(locked=True, archived=True)
            else:
                await thread.send(f"{message.author.mention} {parsed.clarification_question}")
