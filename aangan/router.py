"""Channel router.

Maps a Discord channel name to the handler module responsible for it. Each
household concern is its own channel and its own module (see CLAUDE.md —
"modular by channel"); the router is the single seam between the gateway and
those modules. Register new channels here as their modules are added.
"""

import logging
from typing import Awaitable, Callable

import discord

from aangan.channels.dev import handler as dev_handler

logger = logging.getLogger(__name__)

Handler = Callable[[discord.Message], Awaitable[None]]

# channel name -> handler coroutine
_HANDLERS: dict[str, Handler] = {
    dev_handler.CHANNEL_NAME: dev_handler.handle,
}


async def route(message: discord.Message) -> None:
    channel_name = getattr(message.channel, "name", None)
    handler = _HANDLERS.get(channel_name)
    if handler is None:
        # Message from a channel we don't handle (or a DM) — ignore silently.
        return
    await handler(message)
