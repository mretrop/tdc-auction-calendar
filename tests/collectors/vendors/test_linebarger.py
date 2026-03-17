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
