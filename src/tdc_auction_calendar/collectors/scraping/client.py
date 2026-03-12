"""ScrapeClient — main interface for collectors to fetch and extract web data."""

from __future__ import annotations

import asyncio
import os
import random
from types import TracebackType
from typing import Any
from urllib.parse import urlparse

import structlog
from pydantic import BaseModel

from tdc_auction_calendar.collectors.scraping.cache import ResponseCache
from tdc_auction_calendar.collectors.scraping.extraction import LLMExtraction
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import (
    FetchResult,
    PageFetcher,
)
from tdc_auction_calendar.collectors.scraping.rate_limiter import RateLimiter

logger = structlog.get_logger()


class PermanentFetchError(Exception):
    """Raised for non-retryable errors (e.g., 4xx responses)."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"Permanent error {status_code}: {message}")


class ScrapeError(Exception):
    """Raised when all fetchers fail after retries."""

    def __init__(self, url: str, attempts: list[dict]) -> None:
        self.url = url
        self.attempts = attempts
        super().__init__(f"All fetchers failed for {url}: {len(attempts)} attempts")


class ScrapeResult(BaseModel):
    """Result of a scrape operation."""

    fetch: FetchResult
    data: Any = None
    from_cache: bool = False

    model_config = {"arbitrary_types_allowed": True}


class ScrapeClient:
    """Orchestrates fetching, caching, rate limiting, retries, and extraction."""

    def __init__(
        self,
        primary: PageFetcher,
        fallback: PageFetcher | None = None,
        rate_limiter: RateLimiter | None = None,
        cache: ResponseCache | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._rate_limiter = rate_limiter or RateLimiter()
        self._cache = cache
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    async def __aenter__(self) -> ScrapeClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close fetcher resources."""
        for fetcher in (self._primary, self._fallback):
            if fetcher is not None and hasattr(fetcher, "close"):
                await fetcher.close()

    async def scrape(
        self,
        url: str,
        *,
        render_js: bool = True,
        extraction: Any | None = None,
        schema: type[BaseModel] | None = None,
    ) -> ScrapeResult:
        """Fetch a URL, cache the result, and optionally extract structured data."""
        # 1. Cache check
        if self._cache is not None:
            cached = await self._cache.get(url, render_js)
            if cached is not None:
                data = None
                if extraction is not None or schema is not None:
                    data = await self._run_extraction(cached, extraction, schema)
                return ScrapeResult(fetch=cached, data=data, from_cache=True)

        # 2. Rate limit
        domain = urlparse(url).netloc
        await self._rate_limiter.wait(domain)

        # 3-5. Fetch with retries and fallback
        fetch_result = await self._fetch_with_fallback(url, render_js)

        # 6. Cache store
        if self._cache is not None:
            await self._cache.put(url, render_js, fetch_result)

        # 7. Extract
        data = None
        if extraction is not None or schema is not None:
            data = await self._run_extraction(fetch_result, extraction, schema)

        # 8. Return
        return ScrapeResult(fetch=fetch_result, data=data, from_cache=False)

    async def _fetch_with_fallback(
        self, url: str, render_js: bool
    ) -> FetchResult:
        """Try primary fetcher with retries, then fallback."""
        attempts: list[dict] = []

        for fetcher_name, fetcher in [("primary", self._primary), ("fallback", self._fallback)]:
            if fetcher is None:
                continue

            result = await self._fetch_with_retries(fetcher, fetcher_name, url, render_js, attempts)
            if result is not None:
                return result

        raise ScrapeError(url=url, attempts=attempts)

    async def _fetch_with_retries(
        self,
        fetcher: PageFetcher,
        fetcher_name: str,
        url: str,
        render_js: bool,
        attempts: list[dict],
    ) -> FetchResult | None:
        """Retry a single fetcher with exponential backoff + jitter.

        PermanentFetchError (4xx) is not retried — fails immediately.
        Transient errors (network, 5xx) are retried up to max_retries.
        """
        for attempt in range(self._max_retries):
            try:
                result = await fetcher.fetch(url, render_js=render_js)
                logger.info(
                    "fetch_success",
                    url=url,
                    fetcher=fetcher_name,
                    attempt=attempt + 1,
                )
                return result
            except PermanentFetchError as exc:
                # 4xx errors — do not retry
                attempts.append({
                    "fetcher": fetcher_name,
                    "attempt": attempt + 1,
                    "error": type(exc).__name__,
                    "message": str(exc),
                })
                logger.warning(
                    "fetch_permanent_error",
                    url=url,
                    fetcher=fetcher_name,
                    status_code=exc.status_code,
                )
                return None
            except Exception as exc:
                attempts.append({
                    "fetcher": fetcher_name,
                    "attempt": attempt + 1,
                    "error": type(exc).__name__,
                    "message": str(exc),
                })
                logger.warning(
                    "fetch_retry",
                    url=url,
                    fetcher=fetcher_name,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt < self._max_retries - 1:
                    delay = self._retry_base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)

        return None

    async def _run_extraction(
        self,
        fetch_result: FetchResult,
        extraction: Any | None,
        schema: type[BaseModel] | None,
    ) -> Any:
        """Run extraction on fetched content."""
        if extraction is None and schema is not None:
            extraction = LLMExtraction()

        content = fetch_result.markdown or fetch_result.html or ""
        return await extraction.extract(content, schema=schema)


def create_scrape_client(
    cache_dir: str | None = None,
    cache_ttl: int | None = None,
    rate_limit_default: float | None = None,
    max_retries: int | None = None,
    retry_base_delay: float | None = None,
) -> ScrapeClient:
    """Build a ScrapeClient with default config from env vars.

    If Cloudflare credentials are present, uses CloudflareFetcher as primary
    and Crawl4AiFetcher as fallback. Otherwise, uses Crawl4AiFetcher as primary
    with no fallback.
    """
    from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import (
        Crawl4AiFetcher,
    )

    _cache_dir = cache_dir if cache_dir is not None else os.environ.get("SCRAPE_CACHE_DIR", "data/cache")
    _cache_ttl = cache_ttl if cache_ttl is not None else int(os.environ.get("SCRAPE_CACHE_TTL", "21600"))
    _rate_default = rate_limit_default if rate_limit_default is not None else float(os.environ.get("SCRAPE_RATE_LIMIT_DEFAULT", "2.0"))
    _max_retries = max_retries if max_retries is not None else int(os.environ.get("SCRAPE_RETRY_MAX", "3"))
    _retry_delay = retry_base_delay if retry_base_delay is not None else float(os.environ.get("SCRAPE_RETRY_BASE_DELAY", "1.0"))

    cache = ResponseCache(cache_dir=_cache_dir, ttl=_cache_ttl)
    limiter = RateLimiter(default_delay=_rate_default)

    cf_account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN")

    if cf_account and cf_token:
        from tdc_auction_calendar.collectors.scraping.fetchers.cloudflare import (
            CloudflareFetcher,
        )

        primary = CloudflareFetcher(account_id=cf_account, api_token=cf_token)
        fallback = Crawl4AiFetcher()
    else:
        primary = Crawl4AiFetcher()
        fallback = None

    return ScrapeClient(
        primary=primary,
        fallback=fallback,
        rate_limiter=limiter,
        cache=cache,
        max_retries=_max_retries,
        retry_base_delay=_retry_delay,
    )
