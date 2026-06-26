"""Entry point: start the always-on bot listener.

Loads config, opens the Discord gateway connection, and runs until killed.
Run locally with: python main.py
"""

import asyncio
import logging

from dotenv import load_dotenv

from aangan.bot import create_client
from aangan.config import load_config
from aangan.db import close_db, init_db


async def _run() -> None:
    config = load_config()
    await init_db(config)
    client = create_client()
    try:
        # log_handler=None: let our basicConfig own logging rather than discord.py's.
        await client.start(config.bot_token, reconnect=True)
    finally:
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
