"""The insights agent: an NL question in, a narrated answer out.

Runs a bounded function-calling loop (aangan.llm.run_tool_loop): the model authors
read-only SQL via the run_read_query tool and delivers the answer via the terminal
respond tool. The database does all the math; the model composes queries and narrates.

Phase 2 answers are text only. Empty/NULL results and repeated queries are annotated
in the tool response so the model stops investigating and answers — mode=ANY forces a
tool call every turn, so it can't pause to reason and will otherwise keep querying.
"""

import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from aangan.data import run_read_query
from aangan.insights.charts import ChartSpec, render_chart
from aangan.insights.prompts import build_insights_system
from aangan.llm import ToolLoopExhausted, ToolSpec, run_tool_loop

logger = logging.getLogger(__name__)

__all__ = ["answer", "InsightsAnswer"]


@dataclass
class InsightsAnswer:
    text: str
    chart_png: bytes | None = None

_MAX_ROUNDS = 4
_FALLBACK = "I couldn't work that one out — mind rephrasing?"

_EMPTY_NOTE = (
    "No matching expenses for this query — this is a COMPLETE, VALID result, not an error. "
    "Report it as ₹0 / nothing recorded by calling respond now. Do not run more queries."
)
_DUPLICATE_NOTE = (
    "You already ran this exact query; its result stands. Do not repeat queries — "
    "if the result was empty, report ₹0 via respond; otherwise answer with what you have."
)

_RUN_READ_QUERY_PARAMS = {
    "type": "object",
    "properties": {
        "sql": {
            "type": "string",
            "description": "A single read-only SELECT/WITH query against the expenses table.",
        }
    },
    "required": ["sql"],
}


def _jsonable(rows: list[dict]) -> list[dict]:
    """Rows in JSON-serializable form for the functionResponse. Money is sent as a
    string to avoid float drift; the model only reads it."""
    def conv(v):
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, (datetime.date, datetime.datetime)):
            return v.isoformat()
        return v
    return [{k: conv(v) for k, v in row.items()} for row in rows]


def _is_empty_result(rows: list[dict]) -> bool:
    """True when a query matched nothing: zero rows, or an all-NULL aggregate row
    (SUM/MIN/MAX over no rows returns a single row of NULLs)."""
    return not rows or all(all(v is None for v in row.values()) for row in rows)


def _normalize(sql: str) -> str:
    return " ".join(sql.strip().rstrip(";").lower().split())


def _make_run_read_query_tool() -> tuple[ToolSpec, Callable]:
    """The gather tool. Wraps the read-only DB boundary; annotates empty and
    duplicate results so the model answers instead of investigating in circles."""
    spec = ToolSpec(
        name="run_read_query",
        description=(
            "Execute one read-only SQL query against the expenses table and get the rows back. "
            "Postgres does the arithmetic. Usually one query is enough."
        ),
        parameters=_RUN_READ_QUERY_PARAMS,
    )
    seen: set[str] = set()

    async def impl(sql: str) -> dict:
        if _normalize(sql) in seen:
            return {"note": _DUPLICATE_NOTE}
        seen.add(_normalize(sql))
        try:
            rows = await run_read_query(sql)
        except Exception as e:  # noqa: BLE001 - feed the failure back so the model can fix its SQL
            return {"error": f"{type(e).__name__}: {e}"}
        result = {"row_count": len(rows), "rows": _jsonable(rows)}
        if _is_empty_result(rows):
            result["note"] = _EMPTY_NOTE
        return result

    return spec, impl


def _respond_spec() -> ToolSpec:
    """Terminal tool: the model delivers the answer — a headline, and optionally a
    chart it populates by copying labels + values from the rows it fetched."""
    return ToolSpec(
        name="respond",
        description="Deliver the final answer, based only on rows you fetched.",
        parameters={
            "type": "object",
            "properties": {
                "headline": {
                    "type": "string",
                    "description": "A concise, friendly answer (1-2 sentences). State the ₹ figures from the rows.",
                },
                "chart_type": {
                    "type": "string",
                    "enum": ["none", "bar", "line", "pie"],
                    "description": "A chart to accompany the answer, or 'none' for a single number.",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Chart labels (category/day/week), copied from the rows you fetched.",
                },
                "values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "The ₹ amount for each label, copied EXACTLY from the rows — never rounded or computed.",
                },
                "chart_title": {"type": "string"},
            },
            "required": ["headline", "chart_type"],
        },
        terminal=True,
    )


def _maybe_chart(args: dict) -> bytes | None:
    """Render a chart from the model's respond args, or None. The model supplies
    labels + values (copied from fetched rows); code only renders. Any shape
    mismatch or render failure degrades to text-only — never a wrong chart."""
    kind = args.get("chart_type")
    if kind in (None, "none"):
        return None
    labels = args.get("labels") or []
    values = args.get("values") or []
    if not labels or len(labels) != len(values):
        return None
    try:
        spec = ChartSpec(
            kind=kind,
            title=(args.get("chart_title") or "").strip(),
            labels=[str(x) for x in labels],
            values=[float(v) for v in values],
        )
        return render_chart(spec)
    except Exception:  # noqa: BLE001 - a bad chart must not sink the answer
        logger.exception("Chart render failed; answering text-only")
        return None


async def answer(question: str, today: datetime.date) -> InsightsAnswer:
    """Resolve a spending question to a headline (+ optional chart). Never raises —
    any failure degrades to a graceful fallback so an insights error can't crash the
    handler."""
    rq_spec, rq_impl = _make_run_read_query_tool()
    tools = [rq_spec, _respond_spec()]
    try:
        terminal = await run_tool_loop(
            system=build_insights_system(today),
            user=question,
            tools=tools,
            impls={rq_spec.name: rq_impl},
            max_rounds=_MAX_ROUNDS,
            terminal_fallback="respond",
        )
    except ToolLoopExhausted:
        logger.info("Insights loop exhausted for: %s", question)
        return InsightsAnswer(text=_FALLBACK)
    except Exception:
        logger.exception("Insights agent failed for: %s", question)
        return InsightsAnswer(text=_FALLBACK)

    text = (terminal.args.get("headline") or "").strip() or _FALLBACK
    return InsightsAnswer(text=text, chart_png=_maybe_chart(terminal.args))
