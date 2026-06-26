"""Dev channel handler.

For now it just logs every message it receives — a smoke test that the
gateway connection, intents, and routing are all wired correctly.
"""

import logging

import discord

logger = logging.getLogger(__name__)

CHANNEL_NAME = "dev"


async def handle(message: discord.Message) -> None:
    logger.info(
        "[#%s] %s: %s",
        message.channel.name,
        message.author.display_name,
        message.content,
    )
