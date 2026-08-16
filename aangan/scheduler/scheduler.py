"""Generic in-process job scheduler (tech.md §7).

A "scheduled job" = a recurring CronTrigger + a builder + a target channel.
A job that cares about a reporting period (e.g. the weekly summary) resolves
it itself inside its own build() closure — the scheduler has no notion of
periods. A new job (e.g. the future monthly report) is added by writing one
`build_job(config) -> ScheduledJob` factory elsewhere and registering it in
_build_jobs() below — nothing else here changes.

Restart-safety: the schedule itself needs no persistence. Every process
start re-registers the same CronTriggers identically from code, so a
restart (a deploy, a crash) never loses "when this job should next fire" —
there's no persistent jobstore because there's no dynamic job state that
could be lost. Known limitation, accepted rather than solved: if the
process happens to be down for the exact instant a trigger would have
fired, that one firing is simply skipped — the next one happens on
schedule as normal. Recovering a missed firing would need its own
idempotency/catch-up mechanism; that's more than this needs today.
"""

import io
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from aangan.config.config import Config
from aangan.insights.answer import ChannelMessage
from aangan.timeutil import HOUSEHOLD_TZ

logger = logging.getLogger(__name__)

__all__ = ["ScheduledJob", "init_scheduler", "shutdown_scheduler"]


@dataclass(frozen=True)
class ScheduledJob:
    name: str  # stable id, used for logging
    trigger: CronTrigger
    build: Callable[[], Awaitable[ChannelMessage]]
    channel_id: int


_scheduler: AsyncIOScheduler | None = None


async def _execute(client: discord.Client, job: ScheduledJob) -> None:
    """Build and post one job's message."""
    try:
        message = await job.build()
    except Exception:
        logger.exception("Job %s: failed to build message", job.name)
        return

    try:
        channel = client.get_channel(job.channel_id) or await client.fetch_channel(job.channel_id)
        file = discord.File(io.BytesIO(message.chart_png), filename="chart.png") if message.chart_png else None
        # @everyone so the household is notified regardless of who's online —
        # needs the bot role's "Mention @everyone" permission in the server,
        # or this silently posts without pinging anyone. allowed_mentions is
        # explicit so the ping survives any future stricter default elsewhere.
        await channel.send(
            "@everyone\n" + message.text,
            file=file,
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )
    except Exception:
        logger.exception("Job %s: built message but failed to post", job.name)
        return

    logger.info("Job %s: posted", job.name)


def _build_jobs(config: Config) -> list[ScheduledJob]:
    # Registration point for every scheduled job — mirrors router._HANDLERS.
    # Add the monthly report here later (from aangan.insights.monthly_report
    # import build_job as build_monthly_job) — nothing else in this module
    # changes.
    from aangan.insights.weekly_report import build_job as build_weekly_job
    from aangan.scheduler.reminder import build_job as build_reminder_job
    return [build_weekly_job(config), build_reminder_job(config)]


async def init_scheduler(config: Config, client: discord.Client) -> None:
    """Register all jobs. Safe to call more than once (defense-in-depth
    backstop; the call site in main.py is structured to only ever call this
    once — see main.py)."""
    global _scheduler
    if _scheduler is not None:
        logger.warning("init_scheduler called more than once in this process; ignoring")
        return

    jobs = _build_jobs(config)
    scheduler = AsyncIOScheduler(timezone=HOUSEHOLD_TZ)
    for job in jobs:
        scheduler.add_job(
            _execute, trigger=job.trigger, args=[client, job],
            id=job.name, name=job.name, misfire_grace_time=3600,
        )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler started: %s", [job.name for job in jobs])


async def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
