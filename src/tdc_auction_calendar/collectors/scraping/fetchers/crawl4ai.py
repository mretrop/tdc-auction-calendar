"""Crawl4AI fetcher backend using local headless browser."""

from __future__ import annotations

from typing import Any

import structlog

from tdc_auction_calendar.collectors.scraping.client import PermanentFetchError
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

logger = structlog.get_logger()


class Crawl4AiFetcher:
    """Fetches pages via Crawl4AI's AsyncWebCrawler."""

    def __init__(self, crawler: Any = None) -> None:
        self._crawler = crawler
        self._owns_crawler = crawler is None

    async def _get_crawler(self) -> Any:
        if self._crawler is None:
            from crawl4ai import AsyncWebCrawler

            crawler = AsyncWebCrawler()
            await crawler.__aenter__()
            self._crawler = crawler
        return self._crawler

    async def fetch(self, url: str, *, render_js: bool = True) -> FetchResult:
        """Fetch a page using the local headless browser."""
        logger.info("crawl4ai_fetch_start", url=url, render_js=render_js)

        crawler = await self._get_crawler()
        result = await crawler.arun(url)

        status_code = getattr(result, "status_code", 200)
        if 400 <= status_code < 500:
            raise PermanentFetchError(status_code, f"Crawl4AI got {status_code} for {url}")
        if status_code >= 500:
            raise RuntimeError(f"Crawl4AI got server error {status_code} for {url}")

        return FetchResult(
            url=url,
            html=result.html,
            markdown=result.markdown,
            status_code=status_code,
            fetcher="crawl4ai",
        )

    async def close(self) -> None:
        """Close the crawler if we own it."""
        if self._owns_crawler and self._crawler is not None:
            await self._crawler.__aexit__(None, None, None)
            self._crawler = None
