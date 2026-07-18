"""Unit tests for the chart renderer — no DB, no display."""

import pytest

from aangan.insights import ChartSpec, render_chart

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_bar_renders_png():
    png = render_chart(
        ChartSpec(kind="bar", title="Spend by category", labels=["Groceries", "Dining"], values=[1800.0, 950.0])
    )
    assert png.startswith(_PNG_MAGIC)


def test_line_renders_png():
    png = render_chart(
        ChartSpec(kind="line", title="Weekly total", labels=["W1", "W2", "W3"], values=[4200.0, 3900.0, 5100.0])
    )
    assert png.startswith(_PNG_MAGIC)


def test_mismatched_labels_and_values_rejected():
    with pytest.raises(ValueError):
        ChartSpec(kind="bar", title="t", labels=["a"], values=[1.0, 2.0])


def test_empty_chart_rejected():
    with pytest.raises(ValueError):
        ChartSpec(kind="line", title="t", labels=[], values=[])
