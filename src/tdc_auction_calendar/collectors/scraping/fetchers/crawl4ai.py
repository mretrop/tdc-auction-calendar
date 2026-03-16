"""Crawl4AI fetcher backend using local headless browser."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import structlog

from tdc_auction_calendar.collectors.scraping.client import PermanentFetchError
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

logger = structlog.get_logger()


class StealthLevel(StrEnum):
    """Controls anti-bot evasion level for the Crawl4AI browser."""

    OFF = "off"
    STEALTH = "stealth"
    UNDETECTED = "undetected"


class Crawl4AiFetcher:
    """Fetches pages via Crawl4AI's AsyncWebCrawler."""

    def __init__(
        self,
        crawler: Any = None,
        stealth: StealthLevel = StealthLevel.STEALTH,
    ) -> None:
        self._crawler = crawler
        self._owns_crawler = crawler is None
        self._stealth = stealth

    async def _get_crawler(self) -> Any:
        if self._crawler is None:
            try:
                from crawl4ai import AsyncWebCrawler
                from crawl4ai.async_configs import BrowserConfig
            except ImportError as exc:
                raise RuntimeError(
                    "crawl4ai is required but not installed. Install with: uv add crawl4ai"
                ) from exc

            logger.info("crawl4ai_init", stealth=self._stealth.value)

            if self._stealth == StealthLevel.OFF:
                crawler = AsyncWebCrawler()
            elif self._stealth == StealthLevel.STEALTH:
                browser_config = BrowserConfig(headless=True, enable_stealth=True)
                crawler = AsyncWebCrawler(config=browser_config)
            else:
                # UNDETECTED — uses UndetectedAdapter for tougher bot protection
                from crawl4ai import UndetectedAdapter
                from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

                browser_config = BrowserConfig(headless=True, enable_stealth=True)
                adapter = UndetectedAdapter()
                strategy = AsyncPlaywrightCrawlerStrategy(
                    browser_config=browser_config,
                    browser_adapter=adapter,
                )
                crawler = AsyncWebCrawler(crawler_strategy=strategy)

            try:
                await crawler.__aenter__()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to initialize headless browser: {exc}. "
                    "Try running: crawl4ai-setup"
                ) from exc
            self._crawler = crawler
        return self._crawler

    async def fetch(
        self,
        url: str,
        *,
        render_js: bool = True,
        json_options: dict | None = None,
        js_code: str | None = None,
        wait_for: str | None = None,
    ) -> FetchResult:
        """Fetch a page using the local headless browser."""
        logger.info("crawl4ai_fetch_start", url=url, render_js=render_js)

        crawler = await self._get_crawler()
        try:
            from crawl4ai.async_configs import CrawlerRunConfig

            run_config = CrawlerRunConfig(
                js_code=js_code,
                wait_for=wait_for,
                magic=(self._stealth != StealthLevel.OFF),
            )
            result = await crawler.arun(url, config=run_config)
        except (OSError, RuntimeError):
            raise
        except Exception as exc:
            raise RuntimeError(f"Crawl4AI failed for {url}: {exc}") from exc

        if hasattr(result, "status_code") and result.status_code is not None:
            status_code = result.status_code
        else:
            logger.warning(
                "crawl4ai_missing_status_code",
                url=url,
                result_type=type(result).__name__,
            )
            status_code = 200
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
