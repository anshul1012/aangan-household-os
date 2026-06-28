"""Dev channel handler.

Smoke-tests the full parse pipeline: logs the raw message then calls Gemini
to parse it and logs the structured result.
"""

import datetime
import logging

import discord

from aangan.channels.base import BaseHandler
from aangan.channels.expenses.parsed_entries import ParsedExpense
from aangan.channels.expenses.prompts import build_expense_parse_prompt
from aangan.llm import generate_json

logger = logging.getLogger(__name__)


class DevHandler(BaseHandler):
    CHANNEL_NAME = "dev"

    async def handle_message(self, message: discord.Message) -> None:
        logger.info(
            "[server:%s][channel:%s] %s: %s",
            message.guild.name,
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
        logger.info("Parsed: %s", parsed)

    async def handle_thread(self, message: discord.Message) -> None:
        thread = message.channel
        starter = await thread.parent.fetch_message(thread.id)
        thread_messages = [
            m async for m in thread.history(oldest_first=True, limit=50)
            if m.content.strip()
        ]
        all_messages = [starter] + thread_messages
        logger.info(
            "[server:%s][channel:%s][thread:%s] %d messages:",
            message.guild.name, thread.parent.name, thread.name, len(all_messages),
        )
        for m in all_messages:
            logger.info("  %s: %s", m.author.display_name, m.content)
