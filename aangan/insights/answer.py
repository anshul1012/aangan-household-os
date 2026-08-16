"""Shared answer shape for anything that produces a Discord-postable insight:
the ad-hoc agentic query path (aangan.insights.agent) and scheduled report
jobs (aangan.insights.weekly_report and future siblings) alike."""

from dataclasses import dataclass


@dataclass
class InsightsAnswer:
    text: str
    chart_png: bytes | None = None
