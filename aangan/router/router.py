"""Channel router.

Maps a Discord channel name to the handler module responsible for it. Each
household concern is its own channel and its own module (see CLAUDE.md —
"modular by channel"); the router is the single seam between the gateway and
those modules. Register new channels here as their modules are added.
"""

import logging

import discord

from aangan.channels.base import BaseHandler
from aangan.channels.dev.handler import DevHandler
from aangan.channels.expenses.handler import ExpensesHandler

logger = logging.getLogger(__name__)

_HANDLERS: dict[str, BaseHandler] = {
    DevHandler.CHANNEL_NAME: DevHandler(),
    ExpensesHandler.CHANNEL_NAME: ExpensesHandler(),
}


async def route(message: discord.Message) -> None:
    channel = message.channel
    if isinstance(channel, discord.Thread):
        channel_name = getattr(channel.parent, "name", None)
        handler = _HANDLERS.get(channel_name)
        if handler is None:
            return
        await handler.handle_in_thread(message)
    else:
        channel_name = getattr(channel, "name", None)
        handler = _HANDLERS.get(channel_name)
        if handler is None:
            # Message from a channel we don't handle (or a DM) — ignore silently.
            return
        await handler.handle(message)
