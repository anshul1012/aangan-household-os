"""Nightly unlogged-expense reminder — a stateless nudge, not a report (tech.md §7)."""

import logging

from apscheduler.triggers.cron import CronTrigger

from aangan.config.config import Config
from aangan.insights.answer import ChannelMessage
from aangan.llm import generate_text
from aangan.scheduler.scheduler import ScheduledJob
from aangan.timeutil import HOUSEHOLD_TZ

logger = logging.getLogger(__name__)

__all__ = ["build_job"]

JOB_NAME = "nightly_expense_reminder"

_FALLBACK = "🌙 Daily checkpoint: if a rupee left the house today and hasn't hit the ledger, now's its moment."

_PROMPT = (
    "Write one quirky, lightly humorous 1-2 sentence Discord message reminding a "
    "household to log any expenses from today they haven't logged yet."
    "Tone: warm, playful, a little cheeky — never guilt-trippy or naggy. No generic "
    "'friendly reminder' phrasing. Don't mention specific amounts or categories (you "
    "don't know them). Output only the message, no quotes, no preamble."
)


async def _build() -> ChannelMessage:
    try:
        text = (await generate_text(_PROMPT)).strip() or _FALLBACK
    except Exception:
        logger.exception("Reminder text generation failed; using fallback")
        text = _FALLBACK
    return ChannelMessage(text=text)


def build_job(config: Config) -> ScheduledJob:
    return ScheduledJob(
        name=JOB_NAME,
        trigger=CronTrigger(hour=22, minute=30, timezone=HOUSEHOLD_TZ),
        build=_build,
        channel_id=config.expenses_channel_id,
    )
