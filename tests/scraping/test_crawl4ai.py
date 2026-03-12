"""Tests for Crawl4AiFetcher with mocked AsyncWebCrawler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tdc_auction_calendar.collectors.scraping.client import PermanentFetchError
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


async def test_fetch_4xx_raises_permanent_error():
    """4xx status from crawled page raises PermanentFetchError."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result(status_code=403)

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    with pytest.raises(PermanentFetchError) as exc_info:
        await fetcher.fetch("https://example.com")

    assert exc_info.value.status_code == 403


async def test_fetch_5xx_raises_runtime_error():
    """5xx status from crawled page raises RuntimeError (retryable)."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result(status_code=500)

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    with pytest.raises(RuntimeError, match="server error 500"):
        await fetcher.fetch("https://example.com")


@pytest.fixture
def mock_crawler():
    """Provide a mock AsyncWebCrawler with a default successful result."""
    crawler = AsyncMock()
    crawler.arun.return_value = _mock_crawl_result()
    return crawler


async def test_fetch_passes_js_code_and_wait_for(mock_crawler):
    """Crawl4AI fetcher should pass js_code and wait_for to arun()."""
    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    js = "document.querySelector('#search').click();"
    wait = "#results"

    await fetcher.fetch("https://example.com", js_code=js, wait_for=wait)

    mock_crawler.arun.assert_called_once()
    call_kwargs = mock_crawler.arun.call_args
    assert call_kwargs[0][0] == "https://example.com"
    assert call_kwargs[1].get("js_code") == js
    assert call_kwargs[1].get("wait_for") == wait


async def test_fetch_omits_js_code_when_none(mock_crawler):
    """When js_code/wait_for are None, don't pass them to arun()."""
    fetcher = Crawl4AiFetcher(crawler=mock_crawler)

    await fetcher.fetch("https://example.com")

    call_kwargs = mock_crawler.arun.call_args
    assert "js_code" not in call_kwargs[1]
    assert "wait_for" not in call_kwargs[1]
