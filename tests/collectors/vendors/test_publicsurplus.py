# tests/collectors/vendors/test_publicsurplus.py
"""Tests for PublicSurplus vendor collector."""

from datetime import date
from pathlib import Path

from tdc_auction_calendar.collectors.vendors.publicsurplus import (
    US_STATES,
    _TIME_LEFT_RE,
    extract_county,
    parse_detail_html,
    parse_listing_html,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestExtractCounty:
    def test_county_in_title(self):
        assert extract_county("Tract 4: Norman County Tax-Forfeiture Parcels") == "Norman"

    def test_multi_word_county(self):
        assert extract_county("St Louis County Tax-Forfeiture Parcel") == "St Louis"

    def test_mohave_county_land_sale(self):
        assert extract_county("Mohave County Land Sale - Former Animal Shelter") == "Mohave"

    def test_no_county_returns_various(self):
        assert extract_county("Parcel 2 PIN#26-345-0510") == "Various"

    def test_forfeiture_minimum_bid(self):
        assert extract_county("2025 Forfeiture Minimum Bid Sale: 25-5311-25765") == "Various"

    def test_empty_string(self):
        assert extract_county("") == "Various"


class TestUsStates:
    def test_contains_all_50_states_plus_dc(self):
        assert len(US_STATES) == 51  # 50 states + DC

    def test_mn_is_included(self):
        assert "MN" in US_STATES

    def test_canadian_province_excluded(self):
        assert "AB" not in US_STATES
        assert "ON" not in US_STATES
        assert "BC" not in US_STATES


class TestParseListingHtml:
    def test_extracts_three_auctions(self):
        html = _load("publicsurplus_listing.html")
        results = parse_listing_html(html)
        assert len(results) == 3

    def test_auction_fields(self):
        html = _load("publicsurplus_listing.html")
        results = parse_listing_html(html)
        first = results[0]
        assert first["auction_id"] == "3860102"
        assert first["state"] == "MN"
        assert "Norman County" in first["title"]
        assert first["source_url"] == "https://www.publicsurplus.com/sms/auction/view?auc=3860102"

    def test_extracts_end_date_from_js(self):
        html = _load("publicsurplus_listing.html")
        results = parse_listing_html(html)
        first = results[0]
        # 1773882000000 ms = 2026-03-19 01:00:00 UTC = 2026-03-19
        assert first["end_date"] == date(2026, 3, 19)

    def test_state_is_stripped(self):
        html = _load("publicsurplus_listing.html")
        results = parse_listing_html(html)
        for r in results:
            assert r["state"] == r["state"].strip()
            assert len(r["state"]) == 2

    def test_empty_html(self):
        assert parse_listing_html("") == []


class TestTimeLeftRegex:
    def test_standard_js_call(self):
        js = 'updateTimeLeftSpan(timeLeftInfoMap, 3860102, "3860102catGrid", 1773711883006, 1773882000000, 0, "", "", "catList", timeLeftCallback);'
        m = _TIME_LEFT_RE.search(js)
        assert m is not None
        assert m.group(1) == "3860102"
        assert m.group(2) == "1773882000000"

    def test_extra_whitespace(self):
        js = 'updateTimeLeftSpan( timeLeftInfoMap ,  3860102 ,  "3860102catGrid" ,  1773711883006 ,  1773882000000 , 0, "", "", "catList", timeLeftCallback);'
        m = _TIME_LEFT_RE.search(js)
        assert m is not None
        assert m.group(1) == "3860102"

class TestParseDetailHtml:
    def test_extracts_start_date(self):
        html = _load("publicsurplus_detail.html")
        result = parse_detail_html(html)
        assert result is not None
        assert "start_date" in result
        assert isinstance(result["start_date"], date)
        assert result["start_date"] == date(2026, 3, 4)

    def test_extracts_end_date(self):
        html = _load("publicsurplus_detail.html")
        result = parse_detail_html(html)
        assert result is not None
        assert "end_date" in result
        assert isinstance(result["end_date"], date)
        assert result["end_date"] == date(2026, 3, 18)

    def test_empty_html_returns_none(self):
        assert parse_detail_html("") is None

    def test_html_without_dates_returns_none(self):
        assert parse_detail_html("<html><body>No auction here</body></html>") is None


    def test_no_match_on_unrelated_js(self):
        js = 'console.log("hello world");'
        assert _TIME_LEFT_RE.search(js) is None

    def test_multiline_js_call(self):
        js = """updateTimeLeftSpan(timeLeftInfoMap, 3946030, "3946030catGrid",
            1773711883006, 1773846000000, 0, "",
            "", "catList" , timeLeftCallback);"""
        m = _TIME_LEFT_RE.search(js)
        assert m is not None
        assert m.group(1) == "3946030"
        assert m.group(2) == "1773846000000"


import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tdc_auction_calendar.collectors.vendors.publicsurplus import PublicSurplusCollector
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor


class TestPublicSurplusCollector:
    @pytest.fixture()
    def collector(self):
        return PublicSurplusCollector()

    def test_name(self, collector):
        assert collector.name == "publicsurplus"

    def test_source_type(self, collector):
        assert collector.source_type == SourceType.VENDOR

    def test_normalize_with_county(self, collector):
        raw = {
            "state": "MN",
            "title": "Tract 4: Norman County Tax-Forfeiture Parcels",
            "start_date": date(2026, 3, 17),
            "end_date": date(2026, 3, 19),
            "sale_type": SaleType.DEED,
            "source_url": "https://www.publicsurplus.com/sms/auction/view?auc=3860102",
        }
        auction = collector.normalize(raw)
        assert auction.state == "MN"
        assert auction.county == "Norman"
        assert auction.start_date == date(2026, 3, 17)
        assert auction.end_date == date(2026, 3, 19)
        assert auction.sale_type == SaleType.DEED
        assert auction.source_type == SourceType.VENDOR
        assert auction.vendor == Vendor.PUBLIC_SURPLUS
        assert auction.confidence_score == 0.80
        assert auction.notes == "Tract 4: Norman County Tax-Forfeiture Parcels"

    def test_normalize_without_county(self, collector):
        raw = {
            "state": "MN",
            "title": "Parcel 2 PIN#26-345-0510",
            "start_date": date(2026, 3, 21),
            "end_date": date(2026, 3, 23),
            "sale_type": SaleType.DEED,
            "source_url": "https://www.publicsurplus.com/sms/auction/view?auc=3947401",
        }
        auction = collector.normalize(raw)
        assert auction.county == "Various"

    def test_normalize_lien(self, collector):
        raw = {
            "state": "FL",
            "title": "Tax Lien Certificate Sale",
            "start_date": date(2026, 4, 1),
            "end_date": None,
            "sale_type": SaleType.LIEN,
            "source_url": "https://www.publicsurplus.com/sms/auction/view?auc=9999999",
        }
        auction = collector.normalize(raw)
        assert auction.sale_type == SaleType.LIEN


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


class TestFetch:
    @pytest.fixture()
    def listing_html(self):
        return _load("publicsurplus_listing.html")

    @pytest.fixture()
    def detail_html(self):
        return _load("publicsurplus_detail.html")

    def _make_mock_client(self, listing_html: str, detail_html: str):
        """Create a mock httpx client that returns listing for GET with catid params
        and detail for GET with auction view URLs.

        For listing pages: returns listing_html on the first page request per category,
        then empty HTML on subsequent pages to end pagination. This correctly handles
        both catid=1506 and catid=1505 iterations.
        """
        mock_client = AsyncMock()
        listing_calls: dict[tuple, int] = {}

        async def mock_get(url, **kwargs):
            params = kwargs.get("params", {})
            if "cataucs" in str(url) or "catid" in str(params):
                catid = params.get("catid", "unknown")
                page = params.get("page", 0)
                key = (catid, page)
                listing_calls[key] = listing_calls.get(key, 0) + 1
                if page == 0:
                    return _mock_httpx_response(listing_html)
                return _mock_httpx_response("<html></html>")
            else:
                return _mock_httpx_response(detail_html)

        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    async def test_returns_auctions(self, listing_html, detail_html):
        collector = PublicSurplusCollector()
        mock_client = self._make_mock_client(listing_html, detail_html)
        with patch(
            "tdc_auction_calendar.collectors.vendors.publicsurplus.httpx.AsyncClient",
            return_value=mock_client,
        ):
            auctions = await collector.collect()

        assert len(auctions) > 0
        assert all(a.vendor == Vendor.PUBLIC_SURPLUS for a in auctions)
        assert all(a.source_type == SourceType.VENDOR for a in auctions)
        assert all(a.state in US_STATES for a in auctions)

    async def test_empty_listings_returns_empty(self):
        collector = PublicSurplusCollector()
        mock_client = self._make_mock_client("<html></html>", "<html></html>")
        with patch(
            "tdc_auction_calendar.collectors.vendors.publicsurplus.httpx.AsyncClient",
            return_value=mock_client,
        ):
            auctions = await collector.collect()

        assert auctions == []


@pytest.mark.integration
class TestLiveIntegration:
    async def test_collect_returns_auctions(self):
        """Smoke test against live PublicSurplus site.

        Run with: uv run pytest -m integration -v
        """
        collector = PublicSurplusCollector()
        auctions = await collector.collect()
        for a in auctions:
            assert a.state in US_STATES
            assert a.source_type == SourceType.VENDOR
            assert a.vendor == Vendor.PUBLIC_SURPLUS
            assert a.start_date is not None
            assert a.source_url is not None
