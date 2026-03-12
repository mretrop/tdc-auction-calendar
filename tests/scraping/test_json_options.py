"""Tests for json_options infrastructure support."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import Crawl4AiFetcher
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult


@pytest.mark.asyncio
async def test_crawl4ai_accepts_and_ignores_json_options():
    """Crawl4AiFetcher accepts json_options kwarg without error."""
    mock_crawler = AsyncMock()
    mock_result = MagicMock()
    mock_result.status_code = 200
    mock_result.html = "<h1>Test</h1>"
    mock_result.markdown = "# Test"
    mock_crawler.arun.return_value = mock_result

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    result = await fetcher.fetch(
        "https://example.com",
        json_options={"prompt": "Extract data", "response_format": {}},
    )

    assert result.status_code == 200
    assert result.json is None  # Crawl4AI does not do JSON extraction
