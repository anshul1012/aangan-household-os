"""Dev channel handler.

Smoke-tests the full parse pipeline: logs the raw message then calls Gemini
to parse it and logs the structured result.
"""

import datetime
import logging

import discord

from aangan.channels.base import BaseHandler
from aangan.channels.expenses.parsed_entries import ParsedEntry
from aangan.channels.expenses.prompts import build_expense_parse_prompt
from aangan.llm import generate_json

logger = logging.getLogger(__name__)


class DevHandler(BaseHandler):
    CHANNEL_NAME = "dev"

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
        parsed = await generate_json(prompt, ParsedEntry)
        logger.info("Parsed: %s", parsed)
