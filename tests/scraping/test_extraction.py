"""Tests for extraction strategies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from tdc_auction_calendar.collectors.scraping.extraction import (
    CSSExtraction,
    ExtractionStrategy,
    LLMExtraction,
)


# --- Test schema ---

class AuctionInfo(BaseModel):
    county: str
    date: str
    sale_type: str


# --- LLMExtraction tests ---


async def test_llm_extraction_returns_pydantic_model():
    """LLMExtraction returns a validated Pydantic instance."""
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[
            MagicMock(
                type="tool_use",
                input={"county": "Miami-Dade", "date": "2026-06-01", "sale_type": "deed"},
            )
        ]
    )

    extractor = LLMExtraction(client=mock_client)
    result = await extractor.extract("# Auction\nMiami-Dade deed sale June 1", schema=AuctionInfo)

    assert isinstance(result, AuctionInfo)
    assert result.county == "Miami-Dade"
    assert result.sale_type == "deed"


async def test_llm_extraction_sends_schema_as_tool():
    """LLMExtraction sends the Pydantic schema as a tool definition."""
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[
            MagicMock(
                type="tool_use",
                input={"county": "Harris", "date": "2026-07-01", "sale_type": "deed"},
            )
        ]
    )

    extractor = LLMExtraction(client=mock_client)
    await extractor.extract("some content", schema=AuctionInfo)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    tools = call_kwargs["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "AuctionInfo"


async def test_llm_extraction_requires_schema():
    """LLMExtraction raises ValueError if no schema provided."""
    extractor = LLMExtraction(client=AsyncMock())
    with pytest.raises(ValueError, match="schema"):
        await extractor.extract("content")


async def test_llm_extraction_no_tool_use_block():
    """LLMExtraction raises RuntimeError when Claude returns no tool_use block."""
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text="I couldn't extract the data")]
    )

    extractor = LLMExtraction(client=mock_client)
    with pytest.raises(RuntimeError, match="No tool_use block"):
        await extractor.extract("some content", schema=AuctionInfo)


# --- CSSExtraction tests ---

SAMPLE_HTML = """
<table>
  <tr><td class="county">Miami-Dade</td><td class="date">2026-06-01</td></tr>
  <tr><td class="county">Broward</td><td class="date">2026-07-15</td></tr>
</table>
"""


async def test_css_extraction_returns_list_of_dicts():
    """CSSExtraction extracts data using CSS selectors."""
    extractor = CSSExtraction(
        selectors={"county": "td.county", "date": "td.date"},
        row_selector="tr",
    )
    result = await extractor.extract(SAMPLE_HTML)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["county"] == "Miami-Dade"
    assert result[1]["date"] == "2026-07-15"


async def test_css_extraction_empty_table():
    """CSSExtraction returns empty list when no rows match."""
    extractor = CSSExtraction(
        selectors={"county": "td.county"},
        row_selector="tr.auction-row",
    )
    result = await extractor.extract("<table></table>")
    assert result == []


async def test_css_extraction_ignores_schema():
    """CSSExtraction works regardless of schema parameter."""
    extractor = CSSExtraction(
        selectors={"county": "td.county"},
        row_selector="tr",
    )
    result = await extractor.extract(SAMPLE_HTML, schema=AuctionInfo)
    assert isinstance(result, list)


# --- LLMExtraction enhancement tests (issue #14) ---


async def test_llm_extraction_default_model():
    """Default model is claude-haiku-4-5-20251001."""
    extractor = LLMExtraction(client=AsyncMock())
    assert extractor._model == "claude-haiku-4-5-20251001"


async def test_llm_extraction_on_usage_callback():
    """on_usage callback receives model, schema name, and usage."""
    usage_calls = []

    def on_usage(model, schema_name, usage):
        usage_calls.append((model, schema_name, usage))

    mock_usage = MagicMock()
    mock_usage.input_tokens = 500
    mock_usage.output_tokens = 100

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[
            MagicMock(
                type="tool_use",
                input={"county": "Test", "date": "2026-01-01", "sale_type": "deed"},
            )
        ],
        usage=mock_usage,
    )

    extractor = LLMExtraction(client=mock_client, on_usage=on_usage)
    await extractor.extract("content", schema=AuctionInfo)

    assert len(usage_calls) == 1
    assert usage_calls[0][0] == "claude-haiku-4-5-20251001"
    assert usage_calls[0][1] == "AuctionInfo"
    assert usage_calls[0][2].input_tokens == 500


async def test_llm_extraction_on_usage_fires_before_validation():
    """on_usage fires even if Pydantic validation fails."""
    usage_calls = []

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[
            MagicMock(
                type="tool_use",
                input={"bad_field": "value"},  # Will fail AuctionInfo validation
            )
        ],
        usage=MagicMock(input_tokens=100, output_tokens=50),
    )

    extractor = LLMExtraction(
        client=mock_client,
        on_usage=lambda m, s, u: usage_calls.append((m, s, u)),
    )

    with pytest.raises(Exception):  # Pydantic ValidationError
        await extractor.extract("content", schema=AuctionInfo)

    assert len(usage_calls) == 1


async def test_llm_extraction_api_error():
    """anthropic.APIError is caught and raised as RuntimeError."""
    import anthropic

    mock_client = AsyncMock()
    mock_client.messages.create.side_effect = anthropic.APIError(
        message="rate limited",
        request=MagicMock(),
        body=None,
    )

    extractor = LLMExtraction(client=mock_client)

    with pytest.raises(RuntimeError, match="Claude API error"):
        await extractor.extract("content", schema=AuctionInfo)
