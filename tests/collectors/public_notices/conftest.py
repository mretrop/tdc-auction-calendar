"""Shared test utilities for public notice collector tests."""

import json
from pathlib import Path

from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "public_notices"


def mock_scrape_result(data, url="https://example.com"):
    """Create a ScrapeResult with the given data for testing."""
    return ScrapeResult(
        fetch=FetchResult(
            url=url,
            status_code=200,
            fetcher="crawl4ai",
            html="<div>results</div>",
        ),
        data=data,
    )


def load_fixture(filename):
    """Load a JSON fixture file from the public_notices fixtures directory."""
    return json.loads((FIXTURES_DIR / filename).read_text())
