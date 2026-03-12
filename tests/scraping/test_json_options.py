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
