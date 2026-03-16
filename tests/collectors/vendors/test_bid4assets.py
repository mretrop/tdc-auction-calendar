# tests/collectors/vendors/test_bid4assets.py
"""Tests for Bid4Assets vendor collector."""

from datetime import date

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.vendors.bid4assets import parse_date_range, parse_title
from tdc_auction_calendar.models.enums import SaleType


class TestParseDateRange:
    def test_multi_day_range(self):
        start, end = parse_date_range("May", "May 8th - 12th", 2026)
        assert start == date(2026, 5, 8)
        assert end == date(2026, 5, 12)

    def test_single_day_range(self):
        start, end = parse_date_range("April", "April 8th - 8th", 2026)
        assert start == date(2026, 4, 8)
        assert end is None

    def test_ordinal_suffixes(self):
        start, end = parse_date_range("May", "May 1st - 4th", 2026)
        assert start == date(2026, 5, 1)
        assert end == date(2026, 5, 4)

    def test_ordinal_nd(self):
        start, end = parse_date_range("April", "April 22nd - 22nd", 2026)
        assert start == date(2026, 4, 22)
        assert end is None

    def test_ordinal_rd(self):
        start, end = parse_date_range("May", "May 23rd - 27th", 2026)
        assert start == date(2026, 5, 23)
        assert end == date(2026, 5, 27)

    def test_date_range_without_month_prefix(self):
        start, end = parse_date_range("June", "June 5th - 8th", 2026)
        assert start == date(2026, 6, 5)
        assert end == date(2026, 6, 8)

    def test_cross_month_range(self):
        start, end = parse_date_range("March", "March 30th - 2nd", 2026)
        assert start == date(2026, 3, 30)
        assert end == date(2026, 4, 2)

    def test_invalid_date_range_returns_none(self):
        result = parse_date_range("August", "Tax Sale Dates to be announced soon for August", 2026)
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

    def test_unparseable_returns_none(self):
        result = parse_title("MonroePATaxApr26")
        assert result is None
