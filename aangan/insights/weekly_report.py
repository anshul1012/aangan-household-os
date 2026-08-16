"""Weekly spend summary — the first job riding aangan.scheduler.

Deliberately slim per spec §8.2: total + per-category amount/% share + one
category-breakdown bar chart. No trend/anomaly analysis at weekly grain —
that's monthly-only (deferred, spec §8.3).
"""

import datetime
from decimal import Decimal

from apscheduler.triggers.cron import CronTrigger

from aangan.config.config import Config
from aangan.data.db import fetch_category_totals
from aangan.insights.answer import ChannelMessage
from aangan.insights.charts import ChartSpec, render_chart
from aangan.scheduler.scheduler import ScheduledJob
from aangan.timeutil import HOUSEHOLD_TZ
from aangan.timeutil import now as _now_ist

__all__ = ["build_job"]

JOB_NAME = "weekly_spend_summary"


def _prior_week(now: datetime.datetime) -> tuple[datetime.date, datetime.date]:
    """The most recently completed Mon-Sun week as of `now`. Works for any
    `now`, not just the Monday 10:00 AM fire — a Wednesday catch-up call
    resolves to the same prior full week a Monday-morning cron fire would."""
    today = now.date()
    this_monday = today - datetime.timedelta(days=today.weekday())
    period_end = this_monday - datetime.timedelta(days=1)     # last Sunday
    period_start = period_end - datetime.timedelta(days=6)    # the Monday before it
    return period_start, period_end


def _fmt_date(d: datetime.date) -> str:
    return d.strftime("%d %b")


async def _build() -> ChannelMessage:
    period_start, period_end = _prior_week(_now_ist())
    rows = await fetch_category_totals(period_start, period_end)
    # Highest spend first — a summary is scanned top-to-bottom by a human, so
    # amount-descending is the useful order here. This deliberately deviates
    # from ExpenseCategory's fixed declaration order (used elsewhere as a
    # *parser constraint* fed to the LLM, not a display convention).
    rows.sort(key=lambda r: r.total, reverse=True)

    header = f"📊 **Weekly spend summary — {_fmt_date(period_start)} to {_fmt_date(period_end)}**"
    total = sum((r.total for r in rows), Decimal("0"))

    if not rows or total == 0:
        # Empty week, or a week that net-zeroed out (e.g. spend fully offset
        # by a same-week reimbursement) — skip the % breakdown (0/0) and the
        # chart (ChartSpec requires >=1 data point).
        return ChannelMessage(text=f"{header}\nNo net spend logged this week.")

    lines = [header, f"Total: ₹{total:,.0f} net of reimbursements", ""]
    for r in rows:
        share = r.total / total * 100
        lines.append(f"{r.category:<16} ₹{r.total:,.0f}  ({share:.1f}%)")

    chart = render_chart(ChartSpec(
        kind="bar",
        title="Category breakdown",
        labels=[r.category for r in rows],
        values=[float(r.total) for r in rows],
    ))
    return ChannelMessage(text="\n".join(lines), chart_png=chart)


def build_job(config: Config) -> ScheduledJob:
    return ScheduledJob(
        name=JOB_NAME,
        trigger=CronTrigger(day_of_week="mon", hour=10, minute=0, timezone=HOUSEHOLD_TZ),
        build=_build,
        channel_id=config.insights_channel_id,
    )
