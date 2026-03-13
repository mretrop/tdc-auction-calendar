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


def test_loads_counties_with_urls(collector):
    """Only counties with tax_sale_page_url should be loaded."""
    assert len(collector._county_targets) >= 50
    for target in collector._county_targets:
        assert target["tax_sale_page_url"] is not None
        assert target["state_code"]
        assert target["county_name"]
        assert target["default_sale_type"]


def test_normalize_uses_seed_county_info(collector):
    """State and county should come from seed data, not extraction."""
    target = collector._county_targets[0]
    raw = {"sale_date": "2026-06-15", "sale_type": "lien"}
    auction = collector._normalize_record(raw, target)
    assert auction.state == target["state_code"]
    assert auction.county == target["county_name"]
    assert auction.source_url == target["tax_sale_page_url"]
    assert auction.source_type == SourceType.COUNTY_WEBSITE
    assert auction.confidence_score == 0.70


def test_normalize_falls_back_sale_type(collector):
    """Empty/missing sale_type should use state's default."""
    target = collector._county_targets[0]
    raw = {"sale_date": "2026-06-15", "sale_type": ""}
    auction = collector._normalize_record(raw, target)
    assert auction.sale_type == SaleType(target["default_sale_type"])

    raw_missing = {"sale_date": "2026-06-15"}
    auction2 = collector._normalize_record(raw_missing, target)
    assert auction2.sale_type == SaleType(target["default_sale_type"])


def test_normalize_optional_fields(collector):
    """Optional fields should be parsed when present."""
    target = collector._county_targets[0]
    raw = {
        "sale_date": "2026-06-15",
        "sale_type": "lien",
        "end_date": "2026-06-17",
        "deposit_amount": "5000",
        "registration_deadline": "2026-05-01",
    }
    auction = collector._normalize_record(raw, target)
    assert auction.end_date == date(2026, 6, 17)
    assert auction.deposit_amount == Decimal("5000")
    assert auction.registration_deadline == date(2026, 5, 1)


def test_normalize_optional_fields_absent(collector):
    """Absent optional fields should be None."""
    target = collector._county_targets[0]
    raw = {"sale_date": "2026-06-15"}
    auction = collector._normalize_record(raw, target)
    assert auction.end_date is None
    assert auction.deposit_amount is None
    assert auction.registration_deadline is None
