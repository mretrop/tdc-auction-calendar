# tests/collectors/vendors/test_bid4assets.py
"""Tests for Bid4Assets vendor collector."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.scraping.client import ScrapeError
from tdc_auction_calendar.collectors.vendors.bid4assets import (
    Bid4AssetsCollector,
    parse_calendar_html,
    parse_date_range,
    parse_title,
)
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor


FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestParseDateRange:
    def test_multi_day_range(self):
        start, end = parse_date_range("May 8th - 12th", 2026)
        assert start == date(2026, 5, 8)
        assert end == date(2026, 5, 12)

    def test_single_day_range(self):
        start, end = parse_date_range("April 8th - 8th", 2026)
        assert start == date(2026, 4, 8)
        assert end is None

    def test_ordinal_suffixes(self):
        start, end = parse_date_range("May 1st - 4th", 2026)
        assert start == date(2026, 5, 1)
        assert end == date(2026, 5, 4)

    def test_ordinal_nd(self):
        start, end = parse_date_range("April 22nd - 22nd", 2026)
        assert start == date(2026, 4, 22)
        assert end is None

    def test_ordinal_rd(self):
        start, end = parse_date_range("May 23rd - 27th", 2026)
        assert start == date(2026, 5, 23)
        assert end == date(2026, 5, 27)

    def test_date_range_without_month_prefix(self):
        start, end = parse_date_range("June 5th - 8th", 2026)
        assert start == date(2026, 6, 5)
        assert end == date(2026, 6, 8)

    def test_cross_month_range(self):
        start, end = parse_date_range("March 30th - 2nd", 2026)
        assert start == date(2026, 3, 30)
        assert end == date(2026, 4, 2)

    def test_cross_month_with_both_months_named(self):
        start, end = parse_date_range("October 27th - November 13th", 2025)
        assert start == date(2025, 10, 27)
        assert end == date(2025, 11, 13)

    def test_cross_month_november_december(self):
        start, end = parse_date_range("November 26th - December 5th", 2025)
        assert start == date(2025, 11, 26)
        assert end == date(2025, 12, 5)

    def test_invalid_date_range_returns_none(self):
        result = parse_date_range("Tax Sale Dates to be announced soon for August", 2026)
        assert result is None


class TestParseTitle:
    def test_standard_county(self):
        county, state, sale_type = parse_title(
            "Riverside County, CA Tax Defaulted Properties Auction"
        )
        assert county == "Riverside"
        assert state == "CA"
        assert sale_type == SaleType.DEED

    def test_tax_foreclosed(self):
        county, state, sale_type = parse_title(
            "Klickitat County, WA Tax Foreclosed Properties Auction"
        )
        assert county == "Klickitat"
        assert state == "WA"
        assert sale_type == SaleType.DEED

    def test_tax_title_surplus(self):
        county, state, sale_type = parse_title(
            "Klickitat County, WA Tax Title/Surplus Properties Auction"
        )
        assert county == "Klickitat"
        assert state == "WA"
        assert sale_type == SaleType.DEED

    def test_repository(self):
        county, state, sale_type = parse_title(
            "Monroe County, PA Repository May26"
        )
        assert county == "Monroe"
        assert state == "PA"
        assert sale_type == SaleType.DEED

    def test_tax_lien(self):
        county, state, sale_type = parse_title(
            "Essex County, NJ Tax Lien Certificate Sale"
        )
        assert county == "Essex"
        assert state == "NJ"
        assert sale_type == SaleType.LIEN

    def test_independent_city(self):
        county, state, sale_type = parse_title(
            "Carson City Tax Defaulted Properties Auctions"
        )
        assert county == "Carson City"
        assert state is None
        assert sale_type == SaleType.DEED

    def test_no_county_with_state(self):
        county, state, sale_type = parse_title(
            "Nye County, NV Tax Defaulted Properties Auction"
        )
        assert county == "Nye"
        assert state == "NV"

    def test_unknown_sale_type_defaults_to_deed(self):
        county, state, sale_type = parse_title(
            "Wayne County, MI Special Properties Auction"
        )
        assert county == "Wayne"
        assert state == "MI"
        assert sale_type == SaleType.DEED

    def test_no_county_keyword_with_comma(self):
        """Grays Harbor, WA (no 'County' word)."""
        county, state, sale_type = parse_title(
            "Grays Harbor, WA Tax Foreclosed Properties Auction"
        )
        assert county == "Grays Harbor"
        assert state == "WA"
        assert sale_type == SaleType.DEED

    def test_state_code_repository_no_comma(self):
        """Monroe PA Repository (no comma, no 'County')."""
        county, state, sale_type = parse_title(
            "Monroe PA Repository"
        )
        assert county == "Monroe"
        assert state == "PA"
        assert sale_type == SaleType.DEED

    def test_unparseable_returns_none(self):
        result = parse_title("MonroePATaxApr26")
        assert result is None


class TestBid4AssetsCollector:
    @pytest.fixture()
    def collector(self):
        return Bid4AssetsCollector()

    def test_name(self, collector):
        assert collector.name == "bid4assets"

    def test_source_type(self, collector):
        assert collector.source_type == SourceType.VENDOR

    def test_normalize_standard(self, collector):
        raw = {
            "state": "CA",
            "county": "Riverside",
            "start_date": date(2026, 4, 23),
            "end_date": date(2026, 4, 28),
            "sale_type": SaleType.DEED,
            "source_url": "https://www.bid4assets.com/storefront/RiversideCountyApr26",
        }
        auction = collector.normalize(raw)
        assert auction.state == "CA"
        assert auction.county == "Riverside"
        assert auction.start_date == date(2026, 4, 23)
        assert auction.end_date == date(2026, 4, 28)
        assert auction.sale_type == SaleType.DEED
        assert auction.source_type == SourceType.VENDOR
        assert auction.vendor == Vendor.BID4ASSETS
        assert auction.confidence_score == 0.85

    def test_normalize_single_day(self, collector):
        raw = {
            "state": "PA",
            "county": "Monroe",
            "start_date": date(2026, 4, 8),
            "end_date": None,
            "sale_type": SaleType.DEED,
            "source_url": None,
        }
        auction = collector.normalize(raw)
        assert auction.end_date is None
        assert auction.source_url == "https://www.bid4assets.com/county-tax-sales"

    def test_normalize_lien(self, collector):
        raw = {
            "state": "NJ",
            "county": "Essex",
            "start_date": date(2026, 5, 10),
            "end_date": date(2026, 5, 12),
            "sale_type": SaleType.LIEN,
            "source_url": None,
        }
        auction = collector.normalize(raw)
        assert auction.sale_type == SaleType.LIEN

    def test_normalize_missing_state_skipped(self, collector):
        raw = {
            "state": None,
            "county": "Carson City",
            "start_date": date(2026, 4, 22),
            "end_date": None,
            "sale_type": SaleType.DEED,
            "source_url": None,
        }
        with pytest.raises((ValueError, ValidationError)):
            collector.normalize(raw)


class TestParseCalendarHtml:
    def test_extracts_auctions_from_fixture(self):
        html = _load("bid4assets_calendar.html")
        results = parse_calendar_html(html)
        # March: Alameda CA, Mason WA = 2
        # April: MonroePATaxApr26 (unparseable, skip), Elko NV, Carson City (state=None), Riverside CA = 3
        # May: Nye NV, Klickitat WA x2, Monroe PA = 4
        # June: Santa Cruz CA = 1
        # August: "to be announced" = 0
        assert len(results) == 10

    def test_auction_entry_has_required_fields(self):
        html = _load("bid4assets_calendar.html")
        results = parse_calendar_html(html)
        entry = results[0]
        assert "county" in entry
        assert "state" in entry
        assert "start_date" in entry
        assert "sale_type" in entry

    def test_skips_announced_entries(self):
        html = _load("bid4assets_calendar.html")
        results = parse_calendar_html(html)
        for r in results:
            assert r["start_date"] is not None

    def test_empty_html(self):
        results = parse_calendar_html("")
        assert results == []

    def test_captures_source_url(self):
        html = _load("bid4assets_calendar.html")
        results = parse_calendar_html(html)
        linked = [r for r in results if r.get("source_url")]
        assert len(linked) >= 1

    def test_uses_data_year_attribute(self):
        html = _load("bid4assets_calendar.html")
        results = parse_calendar_html(html)
        # All entries should be in 2026 (from data-year attribute)
        for r in results:
            assert r["start_date"].year == 2026

    def test_skips_unparseable_titles(self):
        """MonroePATaxApr26 slug should be skipped."""
        html = _load("bid4assets_calendar.html")
        results = parse_calendar_html(html)
        counties = [r["county"] for r in results]
        assert "MonroePATaxApr26" not in counties


def _mock_httpx_response(html: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = html
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


@pytest.fixture()
def _mock_client():
    """Helper to create a patched httpx.AsyncClient context."""
    def _make(html: str, status_code: int = 200):
        mock_client = AsyncMock()
        mock_client.get.return_value = _mock_httpx_response(html, status_code)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return patch(
            "tdc_auction_calendar.collectors.vendors.bid4assets.httpx.AsyncClient",
            return_value=mock_client,
        )
    return _make


class TestFetch:
    async def test_returns_auctions(self, _mock_client):
        html = _load("bid4assets_calendar.html")
        collector = Bid4AssetsCollector()
        with _mock_client(html):
            auctions = await collector.collect()

        # 10 parsed - 1 no state (Carson City) - 1 dedup (Klickitat) = 8
        assert len(auctions) == 8
        assert all(a.vendor == Vendor.BID4ASSETS for a in auctions)
        assert all(a.source_type == SourceType.VENDOR for a in auctions)

    async def test_empty_html_raises(self, _mock_client):
        collector = Bid4AssetsCollector()
        with _mock_client(""):
            with pytest.raises(ScrapeError):
                await collector.collect()

    async def test_blocked_response_raises(self, _mock_client):
        """Akamai block page returns 200 but lacks auction-calendar class."""
        collector = Bid4AssetsCollector()
        with _mock_client("<html><body>Access Denied</body></html>"):
            with pytest.raises(ScrapeError):
                await collector.collect()

    async def test_http_error_raises(self, _mock_client):
        collector = Bid4AssetsCollector()
        with _mock_client("blocked", status_code=403):
            with pytest.raises(ScrapeError):
                await collector.collect()

    async def test_filters_none_state_entries(self, _mock_client):
        html = _load("bid4assets_calendar.html")
        collector = Bid4AssetsCollector()
        with _mock_client(html):
            auctions = await collector.collect()

        assert all(a.state is not None for a in auctions)
        assert all(len(a.state) == 2 for a in auctions)


class TestParseDateRangeEdgeCases:
    def test_december_to_january_rollover(self):
        start, end = parse_date_range("December 30th - 2nd", 2025)
        assert start == date(2025, 12, 30)
        assert end == date(2026, 1, 2)

    def test_invalid_month_name_returns_none(self):
        assert parse_date_range("Octber 27th - 30th", 2026) is None

    def test_cross_month_invalid_month_returns_none(self):
        assert parse_date_range("Octber 27th - November 13th", 2026) is None
