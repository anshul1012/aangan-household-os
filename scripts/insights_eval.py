"""Dev harness: run the insights agent over representative NL questions (spec §8.1).

Drives the real agent loop end to end against a local DB, so it validates SQL
authoring, execution through the read-only boundary, and the narrated answer.

    python scripts/insights_eval.py

DB + LLM creds come from the same env as the bot (.env: POSTGRES_* or DATABASE_URL,
GEMINI_API_KEY). Seed some expenses first, or answers will read "nothing recorded".
"""

import asyncio
import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from aangan.config import load_config
from aangan.data.db import close_db, init_db
from aangan.insights.agent import answer
from aangan.llm import init_gemini

QUESTIONS = [
    "how much did we spend last week?",
    "what did we spend between 1 and 15 June?",
    "spend by category this month",
    "how much on groceries at Instamart last week?",
    "top 5 expenses this month",
    "biggest expense in each category this month",
    "which days did we spend the most last month?",
    "how much did Aditi pay this month?",
]


async def main() -> None:
    load_dotenv()
    config = load_config()
    init_gemini(config.gemini_api_key, config.gemini_model)
    await init_db(config)
    today = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).date()
    try:
        for q in QUESTIONS:
            print("\n" + "=" * 78)
            print(f"Q: {q}")
            print(f"A: {await answer(q, today)}")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
