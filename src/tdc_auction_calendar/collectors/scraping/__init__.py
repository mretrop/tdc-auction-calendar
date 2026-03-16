"""Shared scraping infrastructure.

Public API:
    ScrapeClient         — main client for fetching + extracting web data
    ScrapeResult         — result container
    ScrapeError          — raised when all fetchers fail
    PermanentFetchError  — raised for non-retryable errors (4xx)
    create_scrape_client — factory with env-var defaults
    FetchResult          — raw fetch result model
    LLMExtraction        — Claude-based extraction strategy
    CSSExtraction        — CSS selector-based extraction strategy
"""

from tdc_auction_calendar.collectors.scraping.client import (
    ExtractionError,
    PermanentFetchError,
    ScrapeClient,
    ScrapeError,
    ScrapeResult,
    create_scrape_client,
)
from tdc_auction_calendar.collectors.scraping.extraction import (
    CSSExtraction,
    LLMExtraction,
)
from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import StealthLevel
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

__all__ = [
    "CSSExtraction",
    "ExtractionError",
    "FetchResult",
    "LLMExtraction",
    "PermanentFetchError",
    "ScrapeClient",
    "ScrapeError",
    "ScrapeResult",
    "StealthLevel",
    "create_scrape_client",
]
