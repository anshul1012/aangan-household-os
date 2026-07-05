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
from aangan.config import Config

logger = logging.getLogger(__name__)

_HANDLERS: dict[str, BaseHandler] = {
    ExpensesHandler.CHANNEL_NAME: ExpensesHandler(),
}

# Real Discord channel IDs this bot instance is allowed to react in, set at startup
# from config.
_allowed_channel_ids: frozenset[int] = frozenset()

def init_router(config: Config) -> None:
    global _allowed_channel_ids
    _allowed_channel_ids = config.allowed_channel_ids

async def route(message: discord.Message) -> None:
    channel = message.channel
    server = getattr(message.guild, "name", "DM")
    in_thread = isinstance(channel, discord.Thread)
    parent = channel.parent if in_thread else channel
    channel_name = getattr(parent, "name", "None")

    if parent.id not in _allowed_channel_ids:
        return
    handler = _HANDLERS.get(channel_name)
    if handler is None:
        return

    if in_thread:
        logger.info("[%s][#%s][thread:%s] %s: %s", server, channel_name, channel.name, message.author.display_name, message.content)
        await handler.handle_in_thread(message)
    else:
        logger.info("[%s][#%s] %s: %s", server, channel_name, message.author.display_name, message.content)
        await handler.handle(message)
