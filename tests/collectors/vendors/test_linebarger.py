# tests/collectors/vendors/test_linebarger.py
"""Tests for Linebarger vendor collector."""

from tdc_auction_calendar.models.enums import Vendor


def test_linebarger_vendor_exists():
    assert Vendor.LINEBARGER == "Linebarger Goggan Blair & Sampson"
