"""Tests for CountyWebsiteCollector."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdc_auction_calendar.collectors.county_websites.county_collector import (
    CountyWebsiteCollector,
)
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "county_websites"


def _mock_scrape_result(data, url="https://example.com"):
    return ScrapeResult(
        fetch=FetchResult(
            url=url,
            status_code=200,
            fetcher="crawl4ai",
            html="<div>results</div>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return CountyWebsiteCollector()


def test_name(collector):
    assert collector.name == "county_website"


def test_source_type(collector):
    assert collector.source_type == SourceType.COUNTY_WEBSITE
