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
