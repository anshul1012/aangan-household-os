"""Entry point: start the always-on bot listener.

Loads config, opens the Discord gateway connection, and runs until killed.
Run locally with: python main.py
"""

import logging

from dotenv import load_dotenv

from aangan.bot import create_client
from aangan.config import load_config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    # Load .env for local dev. In the container, real env vars are already set
    # and load_dotenv is a no-op (it does not override existing vars).
    load_dotenv()

    config = load_config()
    client = create_client()
    # log_handler=None: let our basicConfig own logging rather than discord.py's.
    client.run(config.bot_token, log_handler=None)


if __name__ == "__main__":
    main()
