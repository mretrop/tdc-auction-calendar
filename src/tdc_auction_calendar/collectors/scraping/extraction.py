"""Extraction strategies for converting page content to structured data."""

from __future__ import annotations

import os
from typing import Any, Protocol

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class ExtractionStrategy(Protocol):
    """Protocol for content extraction strategies."""

    async def extract(
        self, content: str, *, schema: type[BaseModel] | None = None
    ) -> BaseModel | dict | list[dict]: ...


class LLMExtraction:
    """Extracts structured data using Claude's tool_use feature."""

    def __init__(
        self,
        client: Any = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._client = client
        self._model = model

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def extract(
        self, content: str, *, schema: type[BaseModel] | None = None
    ) -> BaseModel:
        """Extract structured data from content using a Pydantic schema."""
        if schema is None:
            raise ValueError("LLMExtraction requires a schema parameter")

        client = self._get_client()
        json_schema = schema.model_json_schema()
        json_schema.pop("title", None)

        tool = {
            "name": schema.__name__,
            "description": f"Extract {schema.__name__} data from the page content.",
            "input_schema": json_schema,
        }

        logger.info("llm_extraction_start", schema=schema.__name__, model=self._model)

        response = await client.messages.create(
            model=self._model,
            max_tokens=1024,
            tools=[tool],
            tool_choice={"type": "tool", "name": schema.__name__},
            messages=[
                {
                    "role": "user",
                    "content": f"Extract structured data from this page content:\n\n{content}",
                }
            ],
        )

        for block in response.content:
            if block.type == "tool_use":
                logger.info("llm_extraction_complete", schema=schema.__name__)
                return schema.model_validate(block.input)

        raise RuntimeError(f"No tool_use block in Claude response for {schema.__name__}")
