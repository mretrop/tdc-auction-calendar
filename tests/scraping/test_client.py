"""Tests for ScrapeClient orchestration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from tdc_auction_calendar.collectors.scraping.cache import ResponseCache
from tdc_auction_calendar.collectors.scraping.client import (
    PermanentFetchError,
    ScrapeClient,
    ScrapeError,
    ScrapeResult,
)
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.collectors.scraping.rate_limiter import RateLimiter


# --- Fixtures ---


def _ok_result(url="https://example.com") -> FetchResult:
    return FetchResult(
        url=url, status_code=200, fetcher="primary",
        html="<h1>Sale</h1>", markdown="# Sale",
    )


@pytest.fixture()
def ok_fetcher():
    """A fetcher that always succeeds."""
    fetcher = AsyncMock()
    fetcher.fetch.return_value = _ok_result()
    fetcher.close = AsyncMock()
    return fetcher


@pytest.fixture()
def failing_fetcher():
    """A fetcher that always raises."""
    fetcher = AsyncMock()
    fetcher.fetch.side_effect = ConnectionError("down")
    fetcher.close = AsyncMock()
    return fetcher


@pytest.fixture()
def rate_limiter():
    return RateLimiter(default_delay=0.0)


@pytest.fixture()
def cache(tmp_path):
    return ResponseCache(cache_dir=str(tmp_path), ttl=3600)


def _make_client(primary, fallback=None, rate_limiter=None, cache=None):
    return ScrapeClient(
        primary=primary,
        fallback=fallback,
        rate_limiter=rate_limiter or RateLimiter(default_delay=0.0),
        cache=cache or MagicMock(),
    )


# --- Tests ---


async def test_scrape_success(ok_fetcher, rate_limiter, cache):
    """Basic scrape returns ScrapeResult with fetch data."""
    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)
    result = await client.scrape("https://example.com")

    assert isinstance(result, ScrapeResult)
    assert result.fetch.status_code == 200
    assert result.from_cache is False


async def test_scrape_uses_cache(ok_fetcher, rate_limiter, cache):
    """Second scrape of same URL returns cached result."""
    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)
    await client.scrape("https://example.com")
    result2 = await client.scrape("https://example.com")

    assert result2.from_cache is True
    # Fetcher called only once (second was cache hit)
    assert ok_fetcher.fetch.call_count == 1


async def test_scrape_fallback_on_primary_failure(failing_fetcher, ok_fetcher, rate_limiter, cache):
    """When primary fails, fallback is tried."""
    ok_fetcher.fetch.return_value = FetchResult(
        url="https://example.com", status_code=200, fetcher="fallback",
        html="<h1>Sale</h1>", markdown="# Sale",
    )
    client = _make_client(failing_fetcher, fallback=ok_fetcher, rate_limiter=rate_limiter, cache=cache)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await client.scrape("https://example.com")

    assert result.fetch.fetcher == "fallback"


async def test_scrape_all_fail_raises_scrape_error(failing_fetcher, rate_limiter, cache):
    """When all fetchers fail, ScrapeError is raised."""
    client = _make_client(failing_fetcher, rate_limiter=rate_limiter, cache=cache)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ScrapeError) as exc_info:
            await client.scrape("https://example.com")

    assert exc_info.value.url == "https://example.com"
    assert len(exc_info.value.attempts) > 0


async def test_scrape_retries_transient_errors(rate_limiter, cache):
    """Transient errors trigger retries before giving up."""
    fetcher = AsyncMock()
    fetcher.fetch.side_effect = [ConnectionError("timeout"), ConnectionError("timeout"), _ok_result()]
    fetcher.close = AsyncMock()

    client = _make_client(fetcher, rate_limiter=rate_limiter, cache=cache)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await client.scrape("https://example.com")

    assert result.fetch.status_code == 200
    assert fetcher.fetch.call_count == 3


async def test_scrape_no_retry_on_permanent_error(rate_limiter, cache):
    """4xx errors (PermanentFetchError) fail immediately without retries."""
    fetcher = AsyncMock()
    fetcher.fetch.side_effect = PermanentFetchError(404, "Not Found")
    fetcher.close = AsyncMock()

    client = _make_client(fetcher, rate_limiter=rate_limiter, cache=cache)

    with pytest.raises(ScrapeError) as exc_info:
        await client.scrape("https://example.com")

    # Should only attempt once — no retries for permanent errors
    assert fetcher.fetch.call_count == 1
    assert len(exc_info.value.attempts) == 1


async def test_scrape_context_manager(ok_fetcher, rate_limiter, cache):
    """ScrapeClient works as async context manager and calls close."""
    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)

    async with client as ctx:
        result = await ctx.scrape("https://example.com")
        assert result.fetch.status_code == 200

    ok_fetcher.close.assert_called_once()


async def test_scrape_with_extraction(ok_fetcher, rate_limiter, cache):
    """Extraction strategy is called on fetched content."""
    extractor = AsyncMock()
    extractor.extract.return_value = {"county": "Miami-Dade"}

    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)
    result = await client.scrape("https://example.com", extraction=extractor)

    extractor.extract.assert_called_once()
    assert result.data == {"county": "Miami-Dade"}


async def test_scrape_schema_without_extraction_defaults_to_llm(ok_fetcher, rate_limiter, cache):
    """Passing schema without extraction creates a default LLMExtraction."""

    class MySchema(BaseModel):
        county: str

    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)

    with patch(
        "tdc_auction_calendar.collectors.scraping.client.LLMExtraction"
    ) as MockLLM:
        mock_instance = AsyncMock()
        mock_instance.extract.return_value = MySchema(county="Test")
        MockLLM.return_value = mock_instance

        result = await client.scrape("https://example.com", schema=MySchema)

    assert result.data.county == "Test"
