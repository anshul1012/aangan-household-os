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
from aangan.channels.expenses.prompts import build_expense_parse_prompt
from aangan.data.db import insert_expense
from aangan.data.models import Expense, ExpenseStatus, MessageSource
from aangan.llm import generate_json

logger = logging.getLogger(__name__)


def _to_expense(parsed: ParsedExpense, message: discord.Message) -> Expense:
    return Expense(
        amount=Decimal(str(parsed.amount)),
        category=parsed.category,
        payer_person=parsed.payer_person,
        raw_text=message.content,
        occurred_on=datetime.date.fromisoformat(parsed.occurred_on),
        tags=parsed.tags,
        source=MessageSource.TEXT,
        confidence=parsed.confidence,
        status=ExpenseStatus.CONFIRMED,
    )


class ExpensesHandler(BaseHandler):
    CHANNEL_NAME = "expenses"

    async def handle_message(self, message: discord.Message) -> None:
        logger.info(
            "[#%s] %s: %s",
            message.channel.name,
            message.author.display_name,
            message.content,
        )

        prompt = build_expense_parse_prompt(
            message=message.content,
            sender=message.author.display_name,
            today=datetime.date.today(),
        )
        parsed = await generate_json(prompt, ParsedExpense)

        if parsed.confidence == ConfidenceLevel.HIGH:
            expense = _to_expense(parsed, message)
            expense_id = await insert_expense(expense)
            logger.info("Saved expense id=%s: %s", expense_id, expense)
        else:
            logger.info(
                "Confidence=%s — clarification needed: %s",
                parsed.confidence,
                parsed.clarification_question,
            )
