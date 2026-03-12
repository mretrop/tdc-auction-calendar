"""Tests for json_options infrastructure support."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tdc_auction_calendar.collectors.scraping.fetchers.cloudflare import CloudflareFetcher
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


@pytest.fixture()
def cf_fetcher():
    return CloudflareFetcher(account_id="test-account", api_token="test-token")


@pytest.mark.asyncio
async def test_cloudflare_json_options_in_post_body(cf_fetcher):
    """json_options adds 'json' to formats and 'jsonOptions' to POST body."""
    json_options = {
        "prompt": "Extract county tax sale dates",
        "response_format": {"type": "object", "properties": {"county": {"type": "string"}}},
    }

    mock_post_resp = httpx.Response(200, json={"id": "job-1"})
    mock_poll_resp = httpx.Response(200, json={
        "status": "completed",
        "result": [{
            "url": "https://example.com",
            "html": "<h1>Sales</h1>",
            "markdown": "# Sales",
            "json": [{"county": "Adams"}],
            "metadata": {"statusCode": 200},
        }],
    })

    with patch.object(cf_fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = mock_post_resp
        mock_http.get.return_value = mock_poll_resp

        result = await cf_fetcher.fetch("https://example.com", json_options=json_options)

    # Verify POST body includes json format and jsonOptions
    call_kwargs = mock_http.post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert "json" in body["formats"]
    assert body["jsonOptions"] == json_options

    # Verify FetchResult has json data
    assert result.json == [{"county": "Adams"}]


@pytest.mark.asyncio
async def test_cloudflare_no_json_options_unchanged(cf_fetcher):
    """Without json_options, CloudflareFetcher behaves as before."""
    mock_post_resp = httpx.Response(200, json={"id": "job-1"})
    mock_poll_resp = httpx.Response(200, json={
        "status": "completed",
        "result": [{
            "url": "https://example.com",
            "html": "<h1>Sales</h1>",
            "markdown": "# Sales",
            "metadata": {"statusCode": 200},
        }],
    })

    with patch.object(cf_fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = mock_post_resp
        mock_http.get.return_value = mock_poll_resp

        result = await cf_fetcher.fetch("https://example.com")

    # Verify POST body does NOT include json format
    call_kwargs = mock_http.post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert "json" not in body["formats"]
    assert "jsonOptions" not in body

    assert result.json is None


# --- ScrapeClient json_options threading tests ---

from tdc_auction_calendar.collectors.scraping.client import ScrapeClient, ScrapeResult
from tdc_auction_calendar.collectors.scraping.cache import ResponseCache
from tdc_auction_calendar.collectors.scraping.rate_limiter import RateLimiter


def _make_fetcher(fetch_result):
    fetcher = AsyncMock()
    fetcher.fetch.return_value = fetch_result
    fetcher.close = AsyncMock()
    return fetcher


@pytest.mark.asyncio
async def test_scrape_threads_json_options_to_fetcher():
    """json_options is passed through to fetcher.fetch()."""
    result = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html="<h1>Data</h1>", json=[{"county": "Adams"}],
    )
    fetcher = _make_fetcher(result)
    client = ScrapeClient(primary=fetcher, rate_limiter=RateLimiter(default_delay=0.0))

    json_opts = {"prompt": "Extract data", "response_format": {}}
    scrape_result = await client.scrape("https://example.com", json_options=json_opts)

    fetcher.fetch.assert_called_once_with(
        "https://example.com", render_js=True, json_options=json_opts,
    )
    assert scrape_result.data == [{"county": "Adams"}]


@pytest.mark.asyncio
async def test_scrape_skips_extraction_when_json_populated():
    """When FetchResult.json is populated, extraction is skipped."""
    result = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html="<h1>Data</h1>", json=[{"county": "Adams"}],
    )
    fetcher = _make_fetcher(result)
    mock_extraction = AsyncMock()
    client = ScrapeClient(primary=fetcher, rate_limiter=RateLimiter(default_delay=0.0))

    scrape_result = await client.scrape(
        "https://example.com",
        json_options={"prompt": "Extract", "response_format": {}},
        extraction=mock_extraction,
    )

    mock_extraction.extract.assert_not_called()
    assert scrape_result.data == [{"county": "Adams"}]


@pytest.mark.asyncio
async def test_scrape_falls_back_to_extraction_when_json_none():
    """When FetchResult.json is None, extraction runs normally."""
    result = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html="<h1>Data</h1>", markdown="# Data",
    )
    fetcher = _make_fetcher(result)
    mock_extraction = AsyncMock()
    mock_extraction.extract.return_value = [{"county": "Adams"}]
    client = ScrapeClient(primary=fetcher, rate_limiter=RateLimiter(default_delay=0.0))

    scrape_result = await client.scrape(
        "https://example.com",
        extraction=mock_extraction,
    )

    mock_extraction.extract.assert_called_once()
    assert scrape_result.data == [{"county": "Adams"}]


@pytest.mark.asyncio
async def test_scrape_bypasses_cache_when_json_options_provided(tmp_path):
    """Cache is bypassed when json_options is provided."""
    # Pre-populate cache with a result that has no json
    cache = ResponseCache(cache_dir=str(tmp_path), ttl=3600)
    cached_result = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html="<h1>Old</h1>",
    )
    await cache.put("https://example.com", True, cached_result)

    # Fetcher returns fresh result with json
    fresh_result = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html="<h1>New</h1>", json=[{"county": "Adams"}],
    )
    fetcher = _make_fetcher(fresh_result)
    client = ScrapeClient(
        primary=fetcher, rate_limiter=RateLimiter(default_delay=0.0), cache=cache,
    )

    scrape_result = await client.scrape(
        "https://example.com",
        json_options={"prompt": "Extract", "response_format": {}},
    )

    # Should have fetched fresh, not used cache
    assert scrape_result.from_cache is False
    assert scrape_result.data == [{"county": "Adams"}]
    fetcher.fetch.assert_called_once()
