"""Expenses channel handler.

Parses each message with Gemini and persists high-confidence entries to the DB.
Mid/low confidence entries are logged with the clarification question for now —
the Discord reply flow is wired up separately.
"""

import datetime
import logging
from decimal import Decimal

import discord

from aangan.channels.base import BaseHandler
from aangan.channels.expenses.parsed_entries import ConfidenceLevel, ParsedExpense
from aangan.channels.expenses.prompts import build_expense_parse_prompt, build_thread_parse_prompt
from aangan.data.db import insert_expense
from aangan.data.models import Expense, ExpenseStatus, MessageSource
from aangan.llm import generate_json

logger = logging.getLogger(__name__)

_THREAD_LIMIT = 50


def _to_expense(parsed: ParsedExpense, raw_text: str) -> Expense:
    return Expense(
        amount=Decimal(str(parsed.amount)),
        category=parsed.category,
        payer_person=parsed.payer_person,
        raw_text=raw_text,
        occurred_on=datetime.date.fromisoformat(parsed.occurred_on),
        tags=parsed.tags,
        source=MessageSource.TEXT,
        confidence=parsed.confidence,
        status=ExpenseStatus.CONFIRMED,
    )

async def _thread_history(thread: discord.Thread) -> list[tuple[str, str]]:
    # The starter message (original expense text) is not in thread history —
    # Discord sets thread.id == starter message id, so fetch it from the parent channel.

    starter = await thread.parent.fetch_message(thread.id)

    thread_messages = [
        m async for m in thread.history(oldest_first=True, limit=_THREAD_LIMIT)
        if m.content.strip()  # skip empty system messages (thread-created events)
    ]

    thread_lines = (
            [(starter.author.display_name, starter.content)]
            + [(m.author.display_name, m.content) for m in thread_messages]
    )
    return thread_lines

async def _persist(parsed: ParsedExpense, raw_text: str) -> int:
    expense = _to_expense(parsed, raw_text)
    expense_id = await insert_expense(expense)
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

        if parsed.amount is not None and parsed.confidence == ConfidenceLevel.HIGH:
            await _persist(parsed, message.content)
            await message.add_reaction("✅")
        else:
            logger.info(
                "Confidence=%s — clarification needed: %s",
                parsed.confidence,
                parsed.clarification_question,
            )
            await message.add_reaction("🤔")
            thread = await message.create_thread(name=message.content[:100])
            await thread.send(f"{message.author.mention} {parsed.clarification_question}")

    async def handle_thread(self, message: discord.Message) -> None:
        thread = message.channel
        if not thread or not isinstance(thread, discord.Thread):
            return

        thread_history = await _thread_history(thread)
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

        if parsed.amount is not None and parsed.confidence == ConfidenceLevel.HIGH:
            await _persist(parsed, raw_text)
            await thread.send("✅ Got it, logged!")
            await thread.edit(locked=True, archived=True)
        else:
            logger.info(
                "Still unclear after thread (confidence=%s): %s",
                parsed.confidence,
                parsed.clarification_question,
            )
            if len(thread_history) < _THREAD_LIMIT:
                await thread.send(f"{message.author.mention} {parsed.clarification_question}")
