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
