"""Chart rendering for insights (shared by ad-hoc queries and scheduled digests).

A single deterministic primitive: ChartSpec in, PNG bytes out. The insights agent
(spec §8.1) chooses the response shape and fills a ChartSpec; code renders it. Chart
guidance follows spec §8.4 — horizontal bars for category breakdowns (readability over
pie), lines for trends over time.
"""

import io
from typing import Literal

import matplotlib

matplotlib.use("Agg")  # headless: no display in the container

import matplotlib.pyplot as plt  # noqa: E402  (must follow the Agg backend selection)
from pydantic import BaseModel, model_validator

__all__ = ["ChartSpec", "render_chart"]


class ChartSpec(BaseModel):
    """A rendering request. Doubles as the structured shape the insights agent
    emits to attach a chart to its answer."""

    kind: Literal["bar", "line"]
    title: str
    labels: list[str]        # bar: category/day names; line: x-axis points (e.g. weeks)
    values: list[float]      # one value per label
    x_label: str | None = None
    y_label: str | None = None

    @model_validator(mode="after")
    def _labels_match_values(self) -> "ChartSpec":
        if len(self.labels) != len(self.values):
            raise ValueError(
                f"labels ({len(self.labels)}) and values ({len(self.values)}) must be equal length"
            )
        if not self.labels:
            raise ValueError("chart needs at least one data point")
        return self


def render_chart(spec: ChartSpec) -> bytes:
    """Render a ChartSpec to PNG bytes."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    try:
        if spec.kind == "bar":
            # Horizontal bar; top-most bar = first label (spec §8.4).
            ax.barh(spec.labels, spec.values, color="#4C72B0")
            ax.invert_yaxis()
        else:  # "line"
            ax.plot(spec.labels, spec.values, marker="o", color="#4C72B0")

        ax.set_title(spec.title)
        if spec.x_label:
            ax.set_xlabel(spec.x_label)
        if spec.y_label:
            ax.set_ylabel(spec.y_label)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        return buf.getvalue()
    finally:
        plt.close(fig)  # release the figure regardless of render outcome
