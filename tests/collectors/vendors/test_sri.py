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
        assert marion.source_url == "https://sriservices.com/properties"

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
