"""Gemini API client.

One public function: generate_json(prompt, schema) → validated Pydantic object.
Call init_gemini() at startup; swap the model via GEMINI_MODEL in .env.
"""

import logging
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: genai.Client | None = None
_model: str = "gemini-2.0-flash"


def init_gemini(api_key: str, model: str = "gemini-2.0-flash") -> None:
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
