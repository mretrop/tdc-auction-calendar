"""Tests for Crawl4AiFetcher with mocked AsyncWebCrawler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import Crawl4AiFetcher


def _mock_crawl_result(html="<h1>Sale</h1>", markdown="# Sale", status_code=200):
    """Create a mock CrawlResult."""
    result = MagicMock()
    result.html = html
    result.markdown = markdown
    result.status_code = status_code
    result.success = status_code == 200
    return result


async def test_fetch_success():
    """Successful fetch returns HTML and markdown from crawler."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result()

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    result = await fetcher.fetch("https://example.com")

    assert result.status_code == 200
    assert result.fetcher == "crawl4ai"
    assert result.html == "<h1>Sale</h1>"
    assert result.markdown == "# Sale"


async def test_fetch_passes_url_to_crawler():
    """The URL is forwarded to the crawler."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result()

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    await fetcher.fetch("https://county.gov/auction")

    mock_crawler.arun.assert_called_once()
    call_args = mock_crawler.arun.call_args
    assert call_args[0][0] == "https://county.gov/auction" or call_args.kwargs.get("url") == "https://county.gov/auction"


async def test_fetch_error_propagates():
    """Crawler errors propagate as exceptions."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = RuntimeError("Browser crashed")

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    with pytest.raises(RuntimeError, match="Browser crashed"):
        await fetcher.fetch("https://example.com")
