"""Extraction strategies for converting page content to structured data."""

from __future__ import annotations

from html.parser import HTMLParser
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


class _SimpleHTMLExtractor(HTMLParser):
    """Minimal HTML parser that emits open-tag and close-tag events as a flat list."""

    def __init__(self) -> None:
        super().__init__()
        self._events: list[dict] = []
        self._current_tag: str | None = None
        self._current_classes: list[str] = []
        self._current_text: str = ""
        self._capture = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        classes = (attr_dict.get("class") or "").split()
        # Emit an open event for row-boundary detection
        self._events.append({"type": "open", "tag": tag, "classes": classes})
        self._current_tag = tag
        self._current_classes = classes
        self._capture = True
        self._current_text = ""

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._current_text += data

    def handle_endtag(self, tag: str) -> None:
        if self._capture and tag == self._current_tag:
            self._events.append({
                "type": "close",
                "tag": tag,
                "classes": self._current_classes,
                "text": self._current_text.strip(),
            })
            self._capture = False

    def get_events(self) -> list[dict]:
        return self._events


class CSSExtraction:
    """Extracts data from HTML using simple CSS class selectors.

    Supports selectors in the form 'tag.class' (e.g., 'td.county').
    """

    def __init__(
        self,
        selectors: dict[str, str],
        row_selector: str,
    ) -> None:
        self._selectors = selectors  # field_name -> "tag.class"
        self._row_selector = row_selector  # e.g., "tr"

    def _parse_selector(self, selector: str) -> tuple[str, str | None]:
        """Parse 'tag.class' into (tag, class) or (tag, None)."""
        if "." in selector:
            tag, cls = selector.split(".", 1)
            return tag, cls
        return selector, None

    async def extract(
        self, content: str, *, schema: type[BaseModel] | None = None
    ) -> list[dict]:
        """Extract rows of data from HTML content."""
        parser = _SimpleHTMLExtractor()
        parser.feed(content)
        events = parser.get_events()

        row_tag, row_class = self._parse_selector(self._row_selector)

        # Use open-tag events to detect row boundaries, close-tag events for data
        rows: list[dict[str, str]] = []
        current_row: dict[str, str] | None = None

        for event in events:
            if event["type"] == "open":
                tag, classes = event["tag"], event["classes"]
                if tag == row_tag and (row_class is None or row_class in classes):
                    if current_row is not None:
                        rows.append(current_row)
                    current_row = {}
            elif event["type"] == "close" and current_row is not None:
                tag, classes, text = event["tag"], event["classes"], event["text"]
                for field_name, selector in self._selectors.items():
                    sel_tag, sel_class = self._parse_selector(selector)
                    if tag == sel_tag and (sel_class is None or sel_class in classes):
                        current_row[field_name] = text

        if current_row:
            rows.append(current_row)

        logger.info("css_extraction_complete", rows=len(rows))
        return rows
