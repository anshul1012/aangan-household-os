"""Generic text-plus-optional-chart payload for anything that posts to a
Discord channel: the ad-hoc insights agentic query path
(aangan.insights.agent), scheduled report jobs (aangan.insights.weekly_report
and future siblings), and non-report scheduled jobs (aangan.scheduler.reminder
and future siblings) alike. Not insight-specific despite the package it lives
in — a nudge or a reminder is just as much a ChannelMessage as a report."""

from dataclasses import dataclass


@dataclass
class ChannelMessage:
    text: str
    chart_png: bytes | None = None
