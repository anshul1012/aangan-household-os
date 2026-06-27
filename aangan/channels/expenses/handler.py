"""Expenses channel handler.

For now it just logs every message it receives — a smoke test that the
gateway connection, intents, and routing are all wired correctly.
"""

import logging

import discord

from aangan.channels.base import BaseHandler

logger = logging.getLogger(__name__)


class ExpensesHandler(BaseHandler):
    CHANNEL_NAME = "expenses"

    async def handle_message(self, message: discord.Message) -> None:
        logger.info(
            "[#%s] %s: %s",
            message.channel.name,
            message.author.display_name,
            message.content,
        )
