"""Chart rendering for insights.

A single deterministic primitive: ChartSpec in, PNG bytes out. The insights agent
picks the chart type and supplies labels + values (copied from the rows it fetched);
code renders. Styled to sit in Discord's dark theme.

- bar  → horizontal bars with ₹ value labels (breakdowns, top-N)
- line → trend over time with ₹ labels
- pie  → donut with ₹ + % per slice (share of a total; few categories)
"""

import io
from typing import Literal

import matplotlib

matplotlib.use("Agg")  # headless: no display in the container

import matplotlib.pyplot as plt  # noqa: E402  (must follow the Agg backend selection)
from pydantic import BaseModel, model_validator  # noqa: E402

__all__ = ["ChartSpec", "render_chart"]

# Discord-dark theme — sits cleanly in the channel.
_BG = "#2b2d31"       # embed-matched background
_FG = "#e3e5e8"       # light text
_MUTED = "#b5bac1"
_GRID = "#3f4147"
_PALETTE = ["#5865F2", "#57F287", "#FEE75C", "#EB459E", "#ED4245", "#1ABC9C", "#E67E22"]

plt.rcParams.update({
    "figure.facecolor": _BG,
    "axes.facecolor": _BG,
    "savefig.facecolor": _BG,
    "text.color": _FG,
    "axes.labelcolor": _MUTED,
    "axes.edgecolor": _GRID,
    "xtick.color": _MUTED,
    "ytick.color": _FG,
    "axes.titlecolor": _FG,
    "axes.titlesize": 15,
    "axes.titleweight": "bold",
    "font.size": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 200,
})


def _rupee(v: float) -> str:
    return f"₹{v:,.0f}"


class ChartSpec(BaseModel):
    kind: Literal["bar", "line", "pie"]
    title: str
    labels: list[str]        # category/day/week names, or pie slices
    values: list[float]      # one ₹ value per label (from the DB rows)

    @model_validator(mode="after")
    def _validate(self) -> "ChartSpec":
        if len(self.labels) != len(self.values):
            raise ValueError(
                f"labels ({len(self.labels)}) and values ({len(self.values)}) must match"
            )
        if not self.labels:
            raise ValueError("chart needs at least one data point")
        return self


def _render_bar(ax, spec: ChartSpec) -> None:
    bars = ax.barh(spec.labels, spec.values, color=_PALETTE)
    ax.invert_yaxis()  # first label on top
    ax.xaxis.set_visible(False)
    for side in ("bottom", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    span = max(spec.values) if spec.values else 0
    for bar, v in zip(bars, spec.values):
        ax.text(bar.get_width() + span * 0.015, bar.get_y() + bar.get_height() / 2,
                _rupee(v), va="center", color=_FG, fontsize=11, fontweight="bold")
    ax.margins(x=0.16)


def _render_line(ax, spec: ChartSpec) -> None:
    ax.plot(spec.labels, spec.values, color=_PALETTE[0], linewidth=2.5, marker="o",
            markersize=7, markerfacecolor=_PALETTE[0], markeredgecolor=_BG, markeredgewidth=1.5)
    ax.fill_between(range(len(spec.labels)), spec.values, color=_PALETTE[0], alpha=0.12)
    ax.grid(axis="y", color=_GRID, linewidth=0.8, alpha=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.set_ylim(bottom=0)
    for i, v in enumerate(spec.values):
        ax.annotate(_rupee(v), (i, v), textcoords="offset points", xytext=(0, 10),
                    ha="center", color=_FG, fontsize=10, fontweight="bold")
    ax.margins(y=0.18)


def _render_pie(ax, spec: ChartSpec) -> None:
    total = sum(spec.values) or 1

    def autopct(pct: float) -> str:
        return f"{_rupee(pct * total / 100)}\n{pct:.0f}%"

    ax.pie(
        spec.values, labels=spec.labels, autopct=autopct,
        colors=_PALETTE, startangle=90, counterclock=False,
        wedgeprops={"width": 0.42, "edgecolor": _BG, "linewidth": 2},
        textprops={"color": _FG, "fontsize": 10},
        pctdistance=0.78,
    )
    ax.set_aspect("equal")


def render_chart(spec: ChartSpec) -> bytes:
    """Render a ChartSpec to PNG bytes."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    try:
        {"bar": _render_bar, "line": _render_line, "pie": _render_pie}[spec.kind](ax, spec)
        ax.set_title(spec.title)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)  # release the figure regardless of outcome
