"""Discord gateway client.

Holds the persistent gateway connection and forwards every incoming message
to the router, which dispatches it to the per-channel handler. This module
knows about Discord; it knows nothing about what any individual channel does.
"""

import logging

import discord

from aangan.router.router import route

logger = logging.getLogger(__name__)


def create_client() -> discord.Client:
    # message_content is a privileged intent and must also be enabled in the
    # Discord Developer Portal for this application. It is what lets the bot
    # read freeform text (and, later, voice attachments) rather than only
    # slash-command arguments.
    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        logger.info("Connected as %s (id=%s)", client.user, client.user.id)

    @client.event
    async def on_message(message: discord.Message) -> None:
        # Never react to our own messages — avoids feedback loops.
        if message.author == client.user:
            return
        await route(message)

    return client
