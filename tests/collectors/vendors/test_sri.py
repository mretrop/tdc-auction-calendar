# tests/collectors/vendors/test_sri.py
"""Tests for SRI Services vendor collector."""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tdc_auction_calendar.collectors.scraping.client import ScrapeError
from tdc_auction_calendar.collectors.vendors.sri import (
    SRICollector,
    _build_source_url,
    parse_api_response,
)
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor


class TestParseApiResponse:
    def test_basic_parsing(self):
        data = [
            {
                "id": 100,
                "saleType": "Tax Sale",
                "saleTypeCode": "A",
                "county": "Marion",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
                "auctionDetail": {
                    "date": "04/07/2026",
                    "time": "10:00 AM",
                    "location": "zeusauction.com",
                    "type": "Online",
                },
            },
            {
                "id": 101,
                "saleType": "Deed Sale",
                "saleTypeCode": "D",
                "county": "Davidson",
                "state": "TN",
                "auctionDate": "2026-04-10T09:00:00",
                "auctionDetail": {
                    "date": "04/10/2026",
                    "time": "09:00 AM",
                    "location": "Court House",
                    "type": "In-person",
                },
            },
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 2
        marion = next(a for a in auctions if a.county == "Marion")
        assert marion.state == "IN"
        assert marion.start_date == date(2026, 4, 7)
        assert marion.sale_type == SaleType.DEED
        assert marion.vendor == Vendor.SRI
        assert marion.confidence_score == 1.0
        assert marion.source_type == SourceType.VENDOR
        assert "sriservices.com/properties?" in marion.source_url
        assert "state=IN" in marion.source_url
        assert "county=Marion" in marion.source_url
        assert "modal=auctionList" in marion.source_url

    def test_filters_excluded_sale_types(self):
        """Only A, C, D, J are kept. F, R, B, O are excluded."""
        data = [
            {
                "id": 1,
                "saleTypeCode": "A",
                "county": "Marion",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
            },
            {
                "id": 2,
                "saleTypeCode": "F",
                "county": "Fulton",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
            },
            {
                "id": 3,
                "saleTypeCode": "R",
                "county": "Clark",
                "state": "IN",
                "auctionDate": "2026-04-08T10:00:00",
            },
            {
                "id": 4,
                "saleTypeCode": "B",
                "county": "Lake",
                "state": "IN",
                "auctionDate": "2026-04-09T10:00:00",
            },
            {
                "id": 5,
                "saleTypeCode": "O",
                "county": "Allen",
                "state": "LA",
                "auctionDate": "2026-04-10T10:00:00",
            },
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 1
        assert auctions[0].county == "Marion"

    def test_sale_type_mapping(self):
        """A/D/J -> DEED, C -> LIEN."""
        data = [
            {"id": 1, "saleTypeCode": "A", "county": "A", "state": "IN", "auctionDate": "2026-04-01T10:00:00"},
            {"id": 2, "saleTypeCode": "C", "county": "B", "state": "IN", "auctionDate": "2026-04-02T10:00:00"},
            {"id": 3, "saleTypeCode": "D", "county": "C", "state": "TN", "auctionDate": "2026-04-03T10:00:00"},
            {"id": 4, "saleTypeCode": "J", "county": "D", "state": "LA", "auctionDate": "2026-04-04T10:00:00"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 4
        by_county = {a.county: a for a in auctions}
        assert by_county["A"].sale_type == SaleType.DEED
        assert by_county["B"].sale_type == SaleType.LIEN
        assert by_county["C"].sale_type == SaleType.DEED
        assert by_county["D"].sale_type == SaleType.DEED

    def test_deduplicates_same_county_date_saletype(self):
        """Same (state, county, date, sale_type) = one Auction."""
        data = [
            {"id": 1, "saleTypeCode": "A", "county": "Marion", "state": "IN", "auctionDate": "2026-04-07T10:00:00"},
            {"id": 2, "saleTypeCode": "A", "county": "Marion", "state": "IN", "auctionDate": "2026-04-07T14:00:00"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 1

    def test_preserves_different_sale_types_same_date(self):
        """Same county+date but different sale types = separate records."""
        data = [
            {"id": 1, "saleTypeCode": "A", "county": "Marion", "state": "IN", "auctionDate": "2026-04-07T10:00:00"},
            {"id": 2, "saleTypeCode": "C", "county": "Marion", "state": "IN", "auctionDate": "2026-04-07T10:00:00"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 2

    def test_empty_response(self):
        assert parse_api_response([]) == []

    def test_skips_missing_auction_date(self):
        data = [
            {"id": 1, "saleTypeCode": "A", "county": "Marion", "state": "IN", "auctionDate": None},
            {"id": 2, "saleTypeCode": "A", "county": "Marion", "state": "IN"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 0

    def test_skips_invalid_date_format(self):
        data = [
            {"id": 1, "saleTypeCode": "A", "county": "Marion", "state": "IN", "auctionDate": "not-a-date"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 0

    def test_skips_unknown_sale_type_code(self):
        """Unknown sale type codes (e.g. 'M') are skipped."""
        data = [
            {"id": 1, "saleTypeCode": "M", "county": "Marion", "state": "IN", "auctionDate": "2026-04-07T10:00:00"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 0

    def test_source_url_is_deep_link(self):
        data = [
            {
                "id": 100,
                "saleTypeCode": "A",
                "county": "Marion",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
            },
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 1
        assert auctions[0].source_url == "https://sriservices.com/properties?state=IN&saleType=tax&county=Marion&modal=auctionList"

    def test_source_url_encodes_county(self):
        data = [
            {
                "id": 100,
                "saleTypeCode": "C",
                "county": "St. Johns",
                "state": "FL",
                "auctionDate": "2026-04-07T10:00:00",
            },
        ]
        auctions = parse_api_response(data)
        assert auctions[0].source_url == "https://sriservices.com/properties?state=FL&saleType=redemption&county=St.+Johns&modal=auctionList"


class TestSRICollector:
    def test_properties(self):
        collector = SRICollector()
        assert collector.name == "sri"
        assert collector.source_type == SourceType.VENDOR

    def test_normalize(self):
        collector = SRICollector()
        raw = {
            "state": "IN",
            "county": "Marion",
            "start_date": date(2026, 4, 7),
            "sale_type": SaleType.DEED,
            "source_url": "https://sriservices.com/properties?state=IN&saleType=tax&county=Marion&modal=auctionList",
        }
        auction = collector.normalize(raw)
        assert auction.state == "IN"
        assert auction.county == "Marion"
        assert auction.start_date == date(2026, 4, 7)
        assert auction.vendor == Vendor.SRI
        assert auction.confidence_score == 1.0
        assert "state=IN" in auction.source_url

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        mock_json = [
            {
                "id": 100,
                "saleTypeCode": "A",
                "county": "Marion",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
            },
            {
                "id": 101,
                "saleTypeCode": "F",
                "county": "Fulton",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
            },
            {
                "id": 102,
                "saleTypeCode": "C",
                "county": "LaPorte",
                "state": "IN",
                "auctionDate": "2026-04-08T10:00:00",
            },
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200

        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            auctions = await collector._fetch()

        # Only A and C kept, F filtered
        assert len(auctions) == 2
        counties = {a.county for a in auctions}
        assert counties == {"Marion", "LaPorte"}

    @pytest.mark.asyncio
    async def test_fetch_sends_correct_request(self):
        """Verify POST body and headers are correct."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200

        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            await collector._fetch()

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://sriservicesusermgmtprod.azurewebsites.net/api/auction/listall"
        body = call_args[1]["json"]
        assert body["recordCount"] == 500
        assert body["auctionDateRange"]["compareOperator"] == ">"
        assert body["auctionDateRange"]["startDate"]  # non-empty date string
        headers = call_args[1]["headers"]
        assert headers["x-api-key"] == "9f8fd9fe5160294175e1c737567030f495d838a7922a678bc06e0a093910"

    @pytest.mark.asyncio
    async def test_fetch_http_error_raises_scrape_error(self):
        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "500", request=httpx.Request("POST", "http://test"), response=httpx.Response(500)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()

    @pytest.mark.asyncio
    async def test_fetch_timeout_raises_scrape_error(self):
        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()

    @pytest.mark.asyncio
    async def test_fetch_json_decode_error_raises_scrape_error(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        mock_response.text = "<html>Server Error</html>"

        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()

    @pytest.mark.asyncio
    async def test_fetch_non_list_response_raises_scrape_error(self):
        """API returning non-list JSON (e.g. error object) is caught."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "something went wrong"}

        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()

    @pytest.mark.asyncio
    async def test_fetch_api_key_error_raises_scrape_error(self):
        """401/403 from API key issues raises ScrapeError."""
        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "401", request=httpx.Request("POST", "http://test"), response=httpx.Response(401)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()


def test_build_source_url():
    url = _build_source_url("FL", "St. Johns", "C")
    assert url == "https://sriservices.com/properties?state=FL&saleType=redemption&county=St.+Johns&modal=auctionList"


def test_sri_in_orchestrator():
    from tdc_auction_calendar.collectors.orchestrator import COLLECTORS
    assert "sri" in COLLECTORS
    assert COLLECTORS["sri"] is SRICollector


def test_sri_vendor_exists():
    assert Vendor.SRI == "SRI"
