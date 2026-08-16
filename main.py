"""Entry point: start the always-on bot listener.

Loads config, opens the Discord gateway connection, and runs until killed.
Run locally with: python main.py
"""

import asyncio
import contextlib
import logging

from dotenv import load_dotenv

from aangan.bot import create_client
from aangan.config import load_config
from aangan.data import close_db, init_db
from aangan.llm import init_gemini
from aangan.router import init_router
from aangan.scheduler import init_scheduler, shutdown_scheduler


async def _run() -> None:
    config = load_config()
    await init_db(config)
    init_gemini(config.gemini_api_key, config.gemini_model)
    init_router(config)
    client = create_client()

    async def _start_scheduler_when_ready() -> None:
        # wait_until_ready() resolves on the first READY only, for this one
        # await — later gateway reconnects re-fire on_ready and toggle
        # discord.py's internal ready Event, but this task has already
        # returned, so init_scheduler() runs exactly once per process.
        await client.wait_until_ready()
        await init_scheduler(config, client)

    # Must be a background task, not a plain await: client.start() below is
    # what actually drives the gateway handshake that resolves
    # wait_until_ready(), so awaiting _start_scheduler_when_ready() here
    # directly would deadlock (waiting on a READY that nothing is producing
    # yet). Kept as a handle so shutdown below can cancel it cleanly.
    scheduler_task = asyncio.create_task(_start_scheduler_when_ready())
    try:
        # log_handler=None: let our basicConfig own logging rather than discord.py's.
        await client.start(config.bot_token, reconnect=True)
    finally:
        # If we're shutting down before READY ever fired, scheduler_task is
        # still parked on wait_until_ready() — cancel it so it doesn't leak,
        # and swallow the resulting CancelledError rather than letting it
        # propagate out of this finally block.
        scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler_task
        await shutdown_scheduler()
        await close_db()
        await client.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    # Load .env for local dev. In the container, real env vars are already set
    # and load_dotenv is a no-op (it does not override existing vars).
    load_dotenv()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
