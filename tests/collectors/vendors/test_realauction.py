"""Tests for RealAuction vendor collector."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.scraping.client import ScrapeError, ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.collectors.vendors.realauction import (
    SITES,
    RealAuctionCollector,
    calendar_url,
    parse_calendar_html,
)
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_extracts_four_auctions():
    html = _load("realauction_hillsborough_march.html")
    results = parse_calendar_html(html)
    assert len(results) == 4


def test_parse_extracts_dates():
    html = _load("realauction_hillsborough_march.html")
    results = parse_calendar_html(html)
    dates = [r["date"] for r in results]
    assert dates == [
        date(2026, 3, 5),
        date(2026, 3, 12),
        date(2026, 3, 19),
        date(2026, 3, 26),
    ]


def test_parse_extracts_sale_type():
    html = _load("realauction_hillsborough_march.html")
    results = parse_calendar_html(html)
    assert all(r["sale_type"] == "Tax Deed" for r in results)


def test_parse_extracts_property_count():
    html = _load("realauction_hillsborough_march.html")
    results = parse_calendar_html(html)
    counts = [r["property_count"] for r in results]
    assert counts == [13, 16, 10, 14]


def test_parse_extracts_time():
    html = _load("realauction_hillsborough_march.html")
    results = parse_calendar_html(html)
    assert all(r["time"] == "10:00 AM ET" for r in results)


def test_parse_empty_calendar():
    html = _load("realauction_apache_empty.html")
    results = parse_calendar_html(html)
    assert results == []


def test_parse_filters_foreclosure():
    html = _load("realauction_miamidade_mixed.html")
    results = parse_calendar_html(html)
    assert len(results) == 1
    assert results[0]["sale_type"] == "Tax Deed"
    assert results[0]["date"] == date(2026, 3, 19)
    assert results[0]["property_count"] == 55


def test_parse_treasurer_deed():
    html = '<div class="CALBOX CALW5 CALSELT" role="link" aria-label="April-15-2026" dayid="04/15/2026"><span class="CALNUM">15</span> <span class="CALTEXT">Treasurer Deed<br><span class="CALMSG"><span class="CALACT">0</span> / <span class="CALSCH">5</span> TD<br> </span><span class="CALTIME"> 10:00 AM MT</span></span></div>'
    results = parse_calendar_html(html)
    assert len(results) == 1
    assert results[0]["sale_type"] == "Treasurer Deed"
    assert results[0]["date"] == date(2026, 4, 15)


def test_parse_none_html():
    results = parse_calendar_html("")
    assert results == []


def test_parse_skips_malformed_date():
    html = '<div class="CALBOX CALW5 CALSELT" role="link" aria-label="03/19/2026" dayid="03/19/2026"><span class="CALNUM">19</span> <span class="CALTEXT">Tax Deed<br><span class="CALMSG"><span class="CALACT">0</span> / <span class="CALSCH">10</span> TD<br> </span><span class="CALTIME"> 10:00 AM ET</span></span></div>'
    results = parse_calendar_html(html)
    assert results == []


def test_parse_non_numeric_property_count():
    html = '<div class="CALBOX CALW5 CALSELT" role="link" aria-label="April-10-2026" dayid="04/10/2026"><span class="CALNUM">10</span> <span class="CALTEXT">Tax Deed<br><span class="CALMSG"><span class="CALACT">0</span> / <span class="CALSCH">N/A</span> TD<br> </span><span class="CALTIME"> 10:00 AM ET</span></span></div>'
    results = parse_calendar_html(html)
    assert len(results) == 1
    assert results[0]["property_count"] == 0


def test_calendar_url_builds_correct_url():
    url = calendar_url("https://hillsborough.realtaxdeed.com", 2026, 4)
    assert url == "https://hillsborough.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar&selCalDate=%7Bts%20%272026-04-01%2000%3A00%3A00%27%7D"


def test_calendar_url_pads_month():
    url = calendar_url("https://apache.realtaxdeed.com", 2026, 3)
    assert "2026-03-01" in url


def test_calendar_url_current_month():
    url = calendar_url("https://hillsborough.realtaxdeed.com")
    assert url == "https://hillsborough.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar"


def test_registry_contains_florida_counties():
    fl_sites = [(s, c, u) for s, c, u in SITES if s == "FL"]
    assert len(fl_sites) >= 37
    counties = {c for _, c, _ in fl_sites}
    assert "Hillsborough" in counties
    assert "Miami-Dade" in counties
    assert "Alachua" in counties


def test_registry_contains_arizona_counties():
    az_sites = [(s, c, u) for s, c, u in SITES if s == "AZ"]
    assert len(az_sites) == 3
    counties = {c for _, c, _ in az_sites}
    assert counties == {"Apache", "Coconino", "Mohave"}


def test_registry_contains_colorado_counties():
    co_sites = [(s, c, u) for s, c, u in SITES if s == "CO"]
    assert len(co_sites) == 8
    assert all("treasurersdeedsale" in u for _, _, u in co_sites)


def test_registry_contains_nj():
    nj_sites = [(s, c, u) for s, c, u in SITES if s == "NJ"]
    assert len(nj_sites) == 2


def test_registry_total_sites():
    assert len(SITES) >= 57


# --- Task 4: RealAuctionCollector unit tests ---


@pytest.fixture()
def collector():
    return RealAuctionCollector()


def test_name(collector):
    assert collector.name == "realauction"


def test_source_type(collector):
    assert collector.source_type == SourceType.VENDOR


def test_normalize_tax_deed(collector):
    raw = {
        "state": "FL",
        "county": "Hillsborough",
        "date": "2026-03-05",
        "sale_type": "Tax Deed",
        "property_count": 13,
        "time": "10:00 AM ET",
        "source_url": "https://hillsborough.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar",
    }
    auction = collector.normalize(raw)
    assert auction.state == "FL"
    assert auction.county == "Hillsborough"
    assert auction.start_date == date(2026, 3, 5)
    assert auction.sale_type == SaleType.DEED
    assert auction.source_type == SourceType.VENDOR
    assert auction.vendor == Vendor.REALAUCTION
    assert auction.confidence_score == 0.90
    assert auction.property_count == 13
    assert "10:00 AM ET" in auction.notes


def test_normalize_treasurer_deed(collector):
    raw = {
        "state": "CO",
        "county": "Denver",
        "date": "2026-04-15",
        "sale_type": "Treasurer Deed",
        "property_count": 5,
        "time": "10:00 AM MT",
        "source_url": "https://denver.treasurersdeedsale.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar",
    }
    auction = collector.normalize(raw)
    assert auction.sale_type == SaleType.DEED
    assert auction.state == "CO"


def test_normalize_missing_field_raises(collector):
    raw = {"state": "FL", "date": "2026-03-05"}
    with pytest.raises((KeyError, ValueError, ValidationError)):
        collector.normalize(raw)


# --- Task 5: _fetch integration tests ---


def _mock_scrape_result(html: str | None) -> ScrapeResult:
    return ScrapeResult(
        fetch=FetchResult(
            url="https://example.realtaxdeed.com/index.cfm",
            status_code=200,
            fetcher="cloudflare",
            html=html,
        ),
    )


async def test_fetch_returns_auctions(collector):
    html = _load("realauction_hillsborough_march.html")
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(html)
    mock_client.close = AsyncMock()

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.create_scrape_client",
            return_value=mock_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.SITES",
            [("FL", "Hillsborough", "https://hillsborough.realtaxdeed.com")],
        ),
    ):
        auctions = await collector.collect()

    # 4 auctions per month * 3 months = 12 (same fixture), dedup -> 4
    assert len(auctions) == 4
    assert all(a.state == "FL" for a in auctions)
    assert all(a.vendor == Vendor.REALAUCTION for a in auctions)


async def test_fetch_empty_html_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result("")
    mock_client.close = AsyncMock()

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.create_scrape_client",
            return_value=mock_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.SITES",
            [("AZ", "Apache", "https://apache.realtaxdeed.com")],
        ),
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_fetch_partial_failure_continues(collector):
    html = _load("realauction_hillsborough_march.html")

    async def mock_scrape(url, **kwargs):
        if "apache" in url:
            raise ScrapeError(url=url, attempts=[{"error": "simulated failure"}])
        return _mock_scrape_result(html)

    mock_client = AsyncMock()
    mock_client.scrape = mock_scrape
    mock_client.close = AsyncMock()

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.create_scrape_client",
            return_value=mock_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.SITES",
            [
                ("AZ", "Apache", "https://apache.realtaxdeed.com"),
                ("FL", "Hillsborough", "https://hillsborough.realtaxdeed.com"),
            ],
        ),
    ):
        auctions = await collector.collect()

    assert len(auctions) == 4
    assert all(a.state == "FL" for a in auctions)


async def test_fetch_mixed_portal_filters_foreclosure(collector):
    html = _load("realauction_miamidade_mixed.html")
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(html)
    mock_client.close = AsyncMock()

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.create_scrape_client",
            return_value=mock_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.SITES",
            [("FL", "Miami-Dade", "https://miamidade.realforeclose.com")],
        ),
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1
    assert auctions[0].county == "Miami-Dade"
    assert auctions[0].sale_type == SaleType.DEED
