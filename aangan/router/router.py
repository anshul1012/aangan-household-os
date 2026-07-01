"""Channel router.

Maps a Discord channel name to the handler module responsible for it. Each
household concern is its own channel and its own module (see CLAUDE.md —
"modular by channel"); the router is the single seam between the gateway and
those modules. Register new channels here as their modules are added.
"""

import logging

import discord

from aangan.channels.base import BaseHandler
from aangan.channels.expenses.handler import ExpensesHandler

logger = logging.getLogger(__name__)

_HANDLERS: dict[str, BaseHandler] = {
    ExpensesHandler.CHANNEL_NAME: ExpensesHandler(),
}


async def route(message: discord.Message) -> None:
    channel = message.channel
    server = getattr(message.guild, "name", "DM")
    if isinstance(channel, discord.Thread):
        channel_name = getattr(channel.parent, "name", None)
        handler = _HANDLERS.get(channel_name)
        if handler is None:
            return
        logger.info("[%s][#%s][thread:%s] %s: %s", server, channel_name, channel.name, message.author.display_name, message.content)
        await handler.handle_in_thread(message)
    else:
        channel_name = getattr(channel, "name", None)
        handler = _HANDLERS.get(channel_name)
        if handler is None:
            return
        logger.info("[%s][#%s] %s: %s", server, channel_name, message.author.display_name, message.content)
        await handler.handle(message)
