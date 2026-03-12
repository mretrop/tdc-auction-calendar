"""Tests for ScrapeClient orchestration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from tdc_auction_calendar.collectors.scraping.cache import ResponseCache
from tdc_auction_calendar.collectors.scraping.client import (
    ExtractionError,
    PermanentFetchError,
    ScrapeClient,
    ScrapeError,
    ScrapeResult,
    create_scrape_client,
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
    if cache is None:
        cache = MagicMock()
        cache.get = AsyncMock(return_value=None)
        cache.put = AsyncMock()
    return ScrapeClient(
        primary=primary,
        fallback=fallback,
        rate_limiter=rate_limiter or RateLimiter(default_delay=0.0),
        cache=cache,
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


async def test_scrape_permanent_error_with_fallback(rate_limiter, cache):
    """PermanentFetchError on primary still tries fallback."""
    primary = AsyncMock()
    primary.fetch.side_effect = PermanentFetchError(404, "Not Found")
    primary.close = AsyncMock()

    fallback = AsyncMock()
    fallback.fetch.return_value = FetchResult(
        url="https://example.com", status_code=200, fetcher="fallback",
        html="<h1>Sale</h1>", markdown="# Sale",
    )
    fallback.close = AsyncMock()

    client = _make_client(primary, fallback=fallback, rate_limiter=rate_limiter, cache=cache)
    result = await client.scrape("https://example.com")

    assert result.fetch.fetcher == "fallback"
    assert primary.fetch.call_count == 1  # no retries


async def test_scrape_extraction_error_raises(ok_fetcher, rate_limiter, cache):
    """Extraction failure wraps in ExtractionError."""
    extractor = AsyncMock()
    extractor.extract.side_effect = RuntimeError("LLM failure")

    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)

    with pytest.raises(ExtractionError, match="LLM failure"):
        await client.scrape("https://example.com", extraction=extractor)


async def test_scrape_extraction_skips_empty_content(rate_limiter, cache):
    """Extraction returns None when fetch has no content."""
    fetcher = AsyncMock()
    fetcher.fetch.return_value = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html=None, markdown=None,
    )
    fetcher.close = AsyncMock()

    extractor = AsyncMock()
    client = _make_client(fetcher, rate_limiter=rate_limiter, cache=cache)
    result = await client.scrape("https://example.com", extraction=extractor)

    assert result.data is None
    extractor.extract.assert_not_called()


def test_scrape_client_rejects_invalid_retries():
    """ScrapeClient constructor rejects max_retries < 1."""
    with pytest.raises(ValueError, match="max_retries"):
        ScrapeClient(primary=AsyncMock(), max_retries=0)


def test_scrape_client_rejects_invalid_retry_delay():
    """ScrapeClient constructor rejects retry_base_delay <= 0."""
    with pytest.raises(ValueError, match="retry_base_delay"):
        ScrapeClient(primary=AsyncMock(), retry_base_delay=0)


async def test_close_handles_fetcher_error(rate_limiter):
    """close() continues even if primary fetcher close() fails."""
    primary = AsyncMock()
    primary.close.side_effect = RuntimeError("cleanup failed")
    fallback = AsyncMock()
    fallback.close = AsyncMock()

    client = _make_client(primary, fallback=fallback, rate_limiter=rate_limiter)
    await client.close()

    # Fallback close was still called despite primary failing
    fallback.close.assert_called_once()


# --- create_scrape_client tests ---


def test_create_scrape_client_crawl4ai_only(tmp_path, monkeypatch):
    """Without Cloudflare env vars, uses Crawl4AiFetcher as primary."""
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    client = create_scrape_client(cache_dir=str(tmp_path))

    from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import Crawl4AiFetcher
    assert isinstance(client._primary, Crawl4AiFetcher)
    assert client._fallback is None


def test_create_scrape_client_with_cloudflare(tmp_path, monkeypatch):
    """With Cloudflare env vars, uses CloudflareFetcher as primary + Crawl4AI fallback."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")

    client = create_scrape_client(cache_dir=str(tmp_path))

    from tdc_auction_calendar.collectors.scraping.fetchers.cloudflare import CloudflareFetcher
    from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import Crawl4AiFetcher
    assert isinstance(client._primary, CloudflareFetcher)
    assert isinstance(client._fallback, Crawl4AiFetcher)


def test_create_scrape_client_explicit_params_override_env(tmp_path, monkeypatch):
    """Explicit parameters override environment variables."""
    monkeypatch.setenv("SCRAPE_RETRY_MAX", "99")

    client = create_scrape_client(cache_dir=str(tmp_path), max_retries=5)

    assert client._max_retries == 5


def test_create_scrape_client_invalid_env_var(tmp_path, monkeypatch):
    """Non-numeric env vars raise clear ValueError."""
    monkeypatch.setenv("SCRAPE_CACHE_TTL", "not-a-number")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    with pytest.raises(ValueError, match="SCRAPE_CACHE_TTL"):
        create_scrape_client(cache_dir=str(tmp_path))
