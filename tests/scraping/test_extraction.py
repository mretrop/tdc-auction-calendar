"""Tests for extraction strategies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from tdc_auction_calendar.collectors.scraping.extraction import (
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
