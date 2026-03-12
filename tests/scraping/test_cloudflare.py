"""Tests for CloudflareFetcher with mocked Cloudflare API."""

import httpx
import pytest
from unittest.mock import patch, AsyncMock

from tdc_auction_calendar.collectors.scraping.fetchers.cloudflare import CloudflareFetcher


@pytest.fixture()
def fetcher():
    """CloudflareFetcher with test credentials."""
    return CloudflareFetcher(account_id="test-account", api_token="test-token")


def _mock_post_response(job_id="job-123"):
    """Mock response for POST /crawl (job creation)."""
    return httpx.Response(200, json={"id": job_id})


def _mock_poll_running():
    """Mock response for GET /crawl/<id> — still running."""
    return httpx.Response(200, json={"status": "running", "result": []})


def _mock_poll_completed(url="https://example.com"):
    """Mock response for GET /crawl/<id> — completed."""
    return httpx.Response(200, json={
        "status": "completed",
        "result": [{
            "url": url,
            "status": "completed",
            "html": "<h1>Auction Sale</h1>",
            "markdown": "# Auction Sale",
            "metadata": {"statusCode": 200},
        }],
    })


def _mock_poll_errored():
    """Mock response for GET /crawl/<id> — errored."""
    return httpx.Response(200, json={"status": "errored", "result": []})


async def test_fetch_success(fetcher):
    """Successful fetch: POST creates job, poll returns completed result."""
    responses = [_mock_post_response(), _mock_poll_completed()]
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = responses[0]
        mock_http.get.return_value = responses[1]

        result = await fetcher.fetch("https://example.com")

    assert result.status_code == 200
    assert result.fetcher == "cloudflare"
    assert result.html == "<h1>Auction Sale</h1>"
    assert result.markdown == "# Auction Sale"


async def test_fetch_polls_until_complete(fetcher):
    """Fetcher polls multiple times before getting completed status."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.side_effect = [_mock_poll_running(), _mock_poll_running(), _mock_poll_completed()]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await fetcher.fetch("https://example.com")

    assert result.status_code == 200
    assert mock_http.get.call_count == 3


async def test_fetch_errored_job_raises(fetcher):
    """Errored job raises an exception."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = _mock_poll_errored()

        with pytest.raises(Exception, match="failed"):
            await fetcher.fetch("https://example.com")


async def test_fetch_no_render(fetcher):
    """render_js=False passes render=False to Cloudflare API."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = _mock_poll_completed()

        await fetcher.fetch("https://example.com", render_js=False)

    call_kwargs = mock_http.post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert body["render"] is False
