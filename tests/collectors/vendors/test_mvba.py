"""Tests for MVBA Law vendor collector."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.collectors.vendors.mvba import (
    MVBACollector,
    parse_monthly_sales,
)
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

# Sample markdown matching the structure from data/research/sub/mvba_upcoming.md
SAMPLE_MARKDOWN = """\
# Monthly Tax Sales

## April Tax Sales (Tuesday, April 7, 2026)

* [Eastland County](https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf)
* [Harrison County (MVBA Online Auction)](https://www.mvbataxsales.com/auction/harrison-county-online-property-tax-sale-april-7-2026-171/bidgallery/)
* [Hill County](https://mvbalaw.com/wp-content/TaxUploads/0426_Hill.pdf)
* [Medina County](https://mvbalaw.com/wp-content/TaxUploads/0426_Medina.pdf)
"""


def test_parse_extracts_date_and_counties():
    results = parse_monthly_sales(SAMPLE_MARKDOWN)
    assert len(results) == 4
    assert all(r[0] == date(2026, 4, 7) for r in results)
    counties = [r[1] for r in results]
    assert counties == ["Eastland", "Harrison", "Hill", "Medina"]


def test_parse_extracts_urls():
    results = parse_monthly_sales(SAMPLE_MARKDOWN)
    assert len(results) == 4
    # Each result is now (date, county, url)
    assert results[0] == (
        date(2026, 4, 7),
        "Eastland",
        "https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf",
    )
    assert results[1] == (
        date(2026, 4, 7),
        "Harrison",
        "https://www.mvbataxsales.com/auction/harrison-county-online-property-tax-sale-april-7-2026-171/bidgallery/",
    )


def test_parse_entry_without_url():
    """County entries without a URL should return None as the third element."""
    md = """\
## April Tax Sales (Tuesday, April 7, 2026)

* [Travis County]
* [Eastland County](https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf)
"""
    results = parse_monthly_sales(md)
    assert len(results) == 2
    assert results[0] == (date(2026, 4, 7), "Travis", None)
    assert results[1][2] == "https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf"


def test_parse_strips_parenthetical_suffixes():
    """County names like 'Harrison County (MVBA Online Auction)' should extract just 'Harrison'."""
    results = parse_monthly_sales(SAMPLE_MARKDOWN)
    counties = [r[1] for r in results]
    assert "Harrison" in counties
    # Should not contain the parenthetical
    assert not any("MVBA" in c for c in counties)


def test_parse_multiple_months():
    md = """\
## March Tax Sales (Tuesday, March 3, 2026)

* [Dallas County](https://example.com/dallas.pdf)

## April Tax Sales (Tuesday, April 7, 2026)

* [Eastland County](https://example.com/eastland.pdf)
* [Hill County](https://example.com/hill.pdf)
"""
    results = parse_monthly_sales(md)
    assert len(results) == 3
    march = [(d, c, u) for d, c, u in results if d == date(2026, 3, 3)]
    april = [(d, c, u) for d, c, u in results if d == date(2026, 4, 7)]
    assert len(march) == 1
    assert march[0][1] == "Dallas"
    assert len(april) == 2


def test_parse_empty_markdown():
    assert parse_monthly_sales("") == []


def test_parse_no_matching_sections():
    md = "# Some other page\n\nNo tax sale info here."
    assert parse_monthly_sales(md) == []


def test_parse_day_name_variations():
    """The heading day name shouldn't matter — we parse the date."""
    md = """\
## May Tax Sales (Wednesday, May 6, 2026)

* [Travis County](https://example.com/travis.pdf)
"""
    results = parse_monthly_sales(md)
    assert len(results) == 1
    assert results[0][:2] == (date(2026, 5, 6), "Travis")


@pytest.fixture()
def collector():
    return MVBACollector()


def test_name(collector):
    assert collector.name == "mvba_vendor"


def test_source_type(collector):
    assert collector.source_type == SourceType.VENDOR


def test_normalize(collector):
    raw = {
        "county": "Eastland",
        "date": "2026-04-07",
        "source_url": "https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf",
    }
    auction = collector.normalize(raw)
    assert auction.state == "TX"
    assert auction.county == "Eastland"
    assert auction.start_date == date(2026, 4, 7)
    assert auction.sale_type == SaleType.DEED
    assert auction.source_type == SourceType.VENDOR
    assert auction.confidence_score == 0.90
    assert auction.vendor == Vendor.MVBA
    assert auction.source_url == "https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf"


def test_normalize_fallback_source_url(collector):
    raw = {
        "county": "Eastland",
        "date": "2026-04-07",
    }
    auction = collector.normalize(raw)
    assert auction.source_url == "https://mvbalaw.com/tax-sales/month-sales/"


def test_normalize_missing_county_raises(collector):
    raw = {"date": "2026-04-07"}
    with pytest.raises((KeyError, ValueError, ValidationError)):
        collector.normalize(raw)


def test_normalize_invalid_date_raises(collector):
    raw = {"county": "Eastland", "date": "not-a-date"}
    with pytest.raises((ValidationError, ValueError)):
        collector.normalize(raw)


def test_parse_heading_with_no_counties():
    """A heading section with no county links should produce no results."""
    md = """\
## April Tax Sales (Tuesday, April 7, 2026)

No counties listed here.
"""
    results = parse_monthly_sales(md)
    assert results == []


def test_parse_invalid_date_skips_section():
    """An invalid date in a heading should skip that section, not crash."""
    md = """\
## April Tax Sales (Tuesday, April 32, 2026)

* [Eastland County](https://example.com/eastland.pdf)

## May Tax Sales (Wednesday, May 6, 2026)

* [Travis County](https://example.com/travis.pdf)
"""
    results = parse_monthly_sales(md)
    assert len(results) == 1
    assert results[0][:2] == (date(2026, 5, 6), "Travis")


# ── _fetch integration tests ─────────────────────────────────────────


def _mock_scrape_result(markdown: str | None) -> ScrapeResult:
    return ScrapeResult(
        fetch=FetchResult(
            url="https://mvbalaw.com/tax-sales/month-sales/",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )


async def test_fetch_returns_auctions(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(SAMPLE_MARKDOWN)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.vendors.mvba.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 4
    assert all(a.state == "TX" for a in auctions)
    assert all(a.source_type == SourceType.VENDOR for a in auctions)
    assert all(a.vendor == Vendor.MVBA for a in auctions)


async def test_fetch_empty_markdown_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result("")
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.vendors.mvba.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_fetch_none_markdown_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(None)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.vendors.mvba.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_fetch_uses_county_urls(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(SAMPLE_MARKDOWN)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.vendors.mvba.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    eastland = next(a for a in auctions if a.county == "Eastland")
    assert eastland.source_url == "https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf"

    harrison = next(a for a in auctions if a.county == "Harrison")
    assert "mvbataxsales.com" in harrison.source_url
