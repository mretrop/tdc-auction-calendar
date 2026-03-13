"""Tests for CloudflareFetcher with mocked Cloudflare API."""

import httpx
import pytest
from unittest.mock import patch, AsyncMock

from tdc_auction_calendar.collectors.scraping.client import PermanentFetchError
from tdc_auction_calendar.collectors.scraping.fetchers.cloudflare import (
    CloudflareFetcher,
    CloudflareFetchError,
)


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


async def test_fetch_post_4xx_raises_permanent_error(fetcher):
    """4xx on job creation raises PermanentFetchError."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = httpx.Response(401, json={"error": "Unauthorized"})

        with pytest.raises(PermanentFetchError) as exc_info:
            await fetcher.fetch("https://example.com")

    assert exc_info.value.status_code == 401


async def test_fetch_post_5xx_raises_cloudflare_error(fetcher):
    """5xx on job creation raises CloudflareFetchError."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = httpx.Response(500, json={"error": "Server Error"})

        with pytest.raises(CloudflareFetchError, match="server error"):
            await fetcher.fetch("https://example.com")


async def test_fetch_poll_timeout(fetcher):
    """Polling timeout raises CloudflareFetchError."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = _mock_poll_running()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch(
                "tdc_auction_calendar.collectors.scraping.fetchers.cloudflare._POLL_TIMEOUT",
                1.0,
            ):
                with patch(
                    "tdc_auction_calendar.collectors.scraping.fetchers.cloudflare._POLL_INTERVAL",
                    0.5,
                ):
                    with pytest.raises(CloudflareFetchError, match="timed out"):
                        await fetcher.fetch("https://example.com")


async def test_fetch_poll_4xx_raises_permanent_error(fetcher):
    """4xx on poll raises PermanentFetchError."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = httpx.Response(401, json={"error": "Unauthorized"})

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(PermanentFetchError) as exc_info:
                await fetcher.fetch("https://example.com")

    assert exc_info.value.status_code == 401


# --- Gap-fill tests: credential validation ---


def test_missing_account_id_raises():
    """CloudflareFetcher requires account_id."""
    with pytest.raises(ValueError, match="CLOUDFLARE_ACCOUNT_ID"):
        CloudflareFetcher(account_id="", api_token="test-token")


def test_missing_api_token_raises():
    """CloudflareFetcher requires api_token."""
    with pytest.raises(ValueError, match="CLOUDFLARE_API_TOKEN"):
        CloudflareFetcher(account_id="test-account", api_token="")


# --- Gap-fill tests: js_code/wait_for rejection ---


async def test_fetch_rejects_js_code(fetcher):
    """Cloudflare fetcher does not support js_code."""
    with pytest.raises(RuntimeError, match="js_code/wait_for"):
        await fetcher.fetch("https://example.com", js_code="document.click()")


async def test_fetch_rejects_wait_for(fetcher):
    """Cloudflare fetcher does not support wait_for."""
    with pytest.raises(RuntimeError, match="js_code/wait_for"):
        await fetcher.fetch("https://example.com", wait_for="#results")


# --- Gap-fill tests: POST error handling ---


async def test_fetch_post_non_json_response_raises(fetcher):
    """Non-JSON response from POST raises CloudflareFetchError."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        resp = httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})
        mock_http.post.return_value = resp

        with pytest.raises(CloudflareFetchError, match="non-JSON"):
            await fetcher.fetch("https://example.com")


async def test_fetch_post_missing_job_id_raises(fetcher):
    """POST response without 'id' raises CloudflareFetchError."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = httpx.Response(200, json={"status": "ok"})

        with pytest.raises(CloudflareFetchError, match="missing 'id'"):
            await fetcher.fetch("https://example.com")


# --- Gap-fill tests: poll error handling ---


async def test_fetch_poll_5xx_raises_cloudflare_error(fetcher):
    """5xx on poll raises CloudflareFetchError."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = httpx.Response(502, json={"error": "Bad Gateway"})

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(CloudflareFetchError, match="server error"):
                await fetcher.fetch("https://example.com")


async def test_fetch_poll_non_json_response_raises(fetcher):
    """Non-JSON poll response raises CloudflareFetchError."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = httpx.Response(
            200, content=b"not json", headers={"content-type": "text/plain"}
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(CloudflareFetchError, match="non-JSON poll"):
                await fetcher.fetch("https://example.com")


async def test_fetch_poll_missing_status_raises(fetcher):
    """Poll response without 'status' raises CloudflareFetchError."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = httpx.Response(200, json={"result": []})

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(CloudflareFetchError, match="missing 'status'"):
                await fetcher.fetch("https://example.com")


# --- Gap-fill tests: completed edge cases ---


async def test_fetch_completed_empty_results_raises(fetcher):
    """Completed job with no results raises CloudflareFetchError."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = httpx.Response(
            200, json={"status": "completed", "result": []}
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(CloudflareFetchError, match="no results"):
                await fetcher.fetch("https://example.com")


async def test_fetch_completed_missing_status_code_defaults_200(fetcher):
    """Completed result without statusCode in metadata defaults to 200."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = httpx.Response(200, json={
            "status": "completed",
            "result": [{
                "url": "https://example.com",
                "html": "<h1>Sale</h1>",
                "markdown": "# Sale",
                "metadata": {},
            }],
        })

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await fetcher.fetch("https://example.com")

    assert result.status_code == 200
    assert result.html == "<h1>Sale</h1>"


async def test_fetch_completed_no_metadata_defaults_200(fetcher):
    """Completed result without metadata key defaults to 200."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = httpx.Response(200, json={
            "status": "completed",
            "result": [{
                "url": "https://example.com",
                "html": "<h1>Sale</h1>",
                "markdown": "# Sale",
            }],
        })

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await fetcher.fetch("https://example.com")

    assert result.status_code == 200


# --- Gap-fill tests: close() ---


async def test_close(fetcher):
    """close() calls aclose() on the HTTP client."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        await fetcher.close()
        mock_http.aclose.assert_called_once()
