"""Gemini API client.

Two usage patterns behind one swappable module:
- generate_json(prompt, schema) → validated Pydantic object (single-shot; the logging parser).
- run_tool_loop(...) → a bounded function-calling loop (the insights agent, spec §8.1).
Call init_gemini() at startup; swap the model via GEMINI_MODEL in .env.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: genai.Client | None = None
_model: str = "gemini-3.1-flash-lite"


def init_gemini(api_key: str, model: str = "gemini-3.1-flash-lite") -> None:
    global _client, _model
    _client = genai.Client(api_key=api_key)
    _model = model
    logger.info("Gemini client initialized (model=%s)", model)


async def generate_json(prompt: str, schema: type[T]) -> T:
    """Send prompt to Gemini and return a validated instance of schema."""
    if _client is None:
        raise RuntimeError("Call init_gemini() before generate_json().")

    response = await _client.aio.models.generate_content(
        model=_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    return schema.model_validate_json(response.text)


# --- Function-calling loop (insights agent, spec §8.1) --------------------


@dataclass
class ToolSpec:
    """A tool the model may call. `parameters` is a JSON schema for the args.
    A `terminal` tool ends the loop: its call args are the loop's result and it
    is never executed (there is no impl for it)."""
    name: str
    description: str
    parameters: dict
    terminal: bool = False


@dataclass
class ToolCall:
    name: str
    args: dict


class ToolLoopExhausted(Exception):
    """The model never called a terminal tool within max_rounds."""


def _to_declaration(spec: ToolSpec) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=spec.name,
        description=spec.description,
        parameters_json_schema=spec.parameters,
    )


def _tools_config(tools: list[ToolSpec], allowed: list[str] | None = None) -> types.GenerateContentConfig:
    fcc = types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.ANY)
    if allowed is not None:
        fcc.allowed_function_names = allowed
    return types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=[_to_declaration(t) for t in tools])],
        tool_config=types.ToolConfig(function_calling_config=fcc),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


async def run_tool_loop(
    system: str,
    user: str,
    tools: list[ToolSpec],
    impls: dict[str, Callable[..., Awaitable[dict]]],
    max_rounds: int = 6,
    terminal_fallback: str | None = None,
) -> ToolCall:
    """Run a bounded function-calling loop and return the terminal tool call.

    mode=ANY forces the model to call a tool every turn, so the loop can only end
    by a terminal tool — never by free-text drift. Non-terminal calls are executed
    via `impls` and their dict results fed back as functionResponses.

    If the round cap is hit without a terminal call and `terminal_fallback` names a
    terminal tool, one final turn is forced (restricted to that tool) so a stuck loop
    still yields an answer; otherwise ToolLoopExhausted is raised."""
    if _client is None:
        raise RuntimeError("Call init_gemini() before run_tool_loop().")

    terminal_names = {t.name for t in tools if t.terminal}
    config = _tools_config(tools)
    config.system_instruction = system
    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=user)])
    ]

    for _ in range(max_rounds):
        response = await _client.aio.models.generate_content(
            model=_model, contents=contents, config=config
        )
        calls = response.function_calls or []
        contents.append(response.candidates[0].content)

        terminal = next((c for c in calls if c.name in terminal_names), None)
        if terminal is not None:
            logger.info("Insights loop terminated via %s", terminal.name)
            return ToolCall(name=terminal.name, args=dict(terminal.args or {}))

        # Execute every non-terminal call and feed the results back.
        response_parts: list[types.Part] = []
        for call in calls:
            args = dict(call.args or {})
            logger.info("Insights tool call: %s(%s)", call.name, args)
            result = await impls[call.name](**args)
            response_parts.append(
                types.Part.from_function_response(name=call.name, response=result)
            )
        contents.append(types.Content(role="user", parts=response_parts))

    if terminal_fallback is not None and terminal_fallback in terminal_names:
        logger.info("Insights loop hit round cap; forcing %s", terminal_fallback)
        forced_config = _tools_config(tools, allowed=[terminal_fallback])
        forced_config.system_instruction = system
        contents.append(types.Content(role="user", parts=[types.Part(
            text="Stop querying now and answer with the information you already have."
        )]))
        response = await _client.aio.models.generate_content(
            model=_model, contents=contents, config=forced_config
        )
        forced = next(
            (c for c in (response.function_calls or []) if c.name == terminal_fallback), None
        )
        if forced is not None:
            return ToolCall(name=forced.name, args=dict(forced.args or {}))

    raise ToolLoopExhausted(f"No terminal tool within {max_rounds} rounds.")
