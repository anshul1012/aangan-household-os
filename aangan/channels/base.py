"""Base class for channel handlers."""

import abc
import logging

import discord

logger = logging.getLogger(__name__)


class BaseHandler(abc.ABC):
    CHANNEL_NAME: str

    async def handle(self, message: discord.Message) -> None:
        try:
            await self.handle_message(message)
        except Exception:
            logger.exception("Unhandled error in %s handler", self.CHANNEL_NAME)

    @abc.abstractmethod
    async def handle_message(self, message: discord.Message) -> None: ...
