# tests/collectors/vendors/test_publicsurplus.py
"""Tests for PublicSurplus vendor collector."""

from tdc_auction_calendar.collectors.vendors.publicsurplus import extract_county


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
