# tests/collectors/vendors/test_linebarger.py
"""Tests for Linebarger vendor collector."""

from tdc_auction_calendar.models.enums import Vendor


def test_linebarger_vendor_exists():
    assert Vendor.LINEBARGER == "Linebarger Goggan Blair & Sampson"


import pytest
from tdc_auction_calendar.collectors.vendors.linebarger import normalize_county_name


class TestNormalizeCountyName:
    def test_single_word(self):
        assert normalize_county_name("DALLAS COUNTY") == "Dallas"

    def test_multi_word(self):
        assert normalize_county_name("FORT BEND COUNTY") == "Fort Bend"

    def test_three_word(self):
        assert normalize_county_name("JIM HOGG COUNTY") == "Jim Hogg"

    def test_already_clean(self):
        assert normalize_county_name("PHILADELPHIA COUNTY") == "Philadelphia"

    def test_no_county_suffix(self):
        assert normalize_county_name("DALLAS") == "Dallas"

    def test_lowercase_input(self):
        assert normalize_county_name("harris county") == "Harris"


from datetime import date
from tdc_auction_calendar.collectors.vendors.linebarger import parse_api_response
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor


class TestParseApiResponse:
    def test_basic_parsing(self):
        data = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
                {
                    "county": "DALLAS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 2
        harris = next(a for a in auctions if a.county == "Harris")
        assert harris.state == "TX"
        assert harris.start_date == date(2026, 4, 7)
        assert harris.sale_type == SaleType.DEED
        assert harris.vendor == Vendor.LINEBARGER
        assert harris.confidence_score == 1.0
        assert harris.source_type == SourceType.VENDOR

    def test_filters_cancelled(self):
        data = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
                {
                    "county": "DALLAS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Cancelled",
                    "precinct": "1",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 1
        assert auctions[0].county == "Harris"

    def test_deduplicates_precincts(self):
        """Same county + date + different precincts = one Auction."""
        data = {
            "count": 3,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "2",
                },
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Online Auction",
                    "precinct": "3",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 1
        assert auctions[0].county == "Harris"

    def test_pa_is_deed(self):
        data = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "PHILADELPHIA COUNTY",
                    "state": "PA",
                    "sale_date_only": "2026-03-24",
                    "status": "Scheduled for Auction",
                    "precinct": "",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 1
        assert auctions[0].sale_type == SaleType.DEED

    def test_source_url_includes_state(self):
        data = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "PHILADELPHIA COUNTY",
                    "state": "PA",
                    "sale_date_only": "2026-03-24",
                    "status": "Scheduled for Auction",
                    "precinct": "",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert auctions[0].source_url == "https://taxsales.lgbs.com/map?area=PA"

    def test_skips_empty_date(self):
        data = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 0

    def test_skips_null_date(self):
        data = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": None,
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 0


from unittest.mock import AsyncMock, patch
import httpx
from tdc_auction_calendar.collectors.scraping.client import ScrapeError
from tdc_auction_calendar.collectors.vendors.linebarger import LinebargerCollector


class TestLinebargerCollector:
    def test_properties(self):
        collector = LinebargerCollector()
        assert collector.name == "linebarger"
        assert collector.source_type == SourceType.VENDOR

    def test_normalize(self):
        collector = LinebargerCollector()
        raw = {
            "state": "TX",
            "county": "Harris",
            "start_date": date(2026, 4, 7),
            "sale_type": SaleType.DEED,
            "source_url": "https://taxsales.lgbs.com/map?area=TX",
        }
        auction = collector.normalize(raw)
        assert auction.state == "TX"
        assert auction.county == "Harris"
        assert auction.start_date == date(2026, 4, 7)
        assert auction.vendor == Vendor.LINEBARGER
        assert auction.confidence_score == 1.0

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        mock_json = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
                {
                    "county": "PHILADELPHIA COUNTY",
                    "state": "PA",
                    "sale_date_only": "2026-03-24",
                    "status": "Scheduled for Auction",
                    "precinct": "",
                },
            ],
        }
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status = lambda: None

        with patch("tdc_auction_calendar.collectors.vendors.linebarger.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = LinebargerCollector()
            auctions = await collector._fetch()

        assert len(auctions) == 2
        counties = {a.county for a in auctions}
        assert counties == {"Harris", "Philadelphia"}

    @pytest.mark.asyncio
    async def test_fetch_http_error_raises_scrape_error(self):
        with patch("tdc_auction_calendar.collectors.vendors.linebarger.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.HTTPStatusError(
                "500", request=httpx.Request("GET", "http://test"), response=httpx.Response(500)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = LinebargerCollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()

    @pytest.mark.asyncio
    async def test_fetch_follows_pagination(self):
        page1 = {
            "count": 2,
            "next": "https://taxsales.lgbs.com/api/filter_bar/?limit=1000&offset=1000",
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
            ],
        }
        page2 = {
            "count": 2,
            "next": None,
            "previous": "https://taxsales.lgbs.com/api/filter_bar/?limit=1000",
            "results": [
                {
                    "county": "DALLAS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
            ],
        }

        resp1 = AsyncMock()
        resp1.json.return_value = page1
        resp1.raise_for_status = lambda: None

        resp2 = AsyncMock()
        resp2.json.return_value = page2
        resp2.raise_for_status = lambda: None

        with patch("tdc_auction_calendar.collectors.vendors.linebarger.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = [resp1, resp2]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = LinebargerCollector()
            auctions = await collector._fetch()

        assert len(auctions) == 2
        assert mock_client.get.call_count == 2


from tdc_auction_calendar.collectors.orchestrator import COLLECTORS


def test_linebarger_in_orchestrator():
    assert "linebarger" in COLLECTORS
    assert COLLECTORS["linebarger"] is LinebargerCollector
