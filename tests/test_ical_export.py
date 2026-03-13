"""Tests for iCalendar exporter."""

from __future__ import annotations

import datetime
from decimal import Decimal

from icalendar import Calendar

from tdc_auction_calendar.exporters.ical import auctions_to_ical
from tdc_auction_calendar.models.auction import Auction


def _make_auction(**overrides) -> Auction:
    """Build an Auction with sensible defaults; override any field."""
    defaults = {
        "state": "FL",
        "county": "Miami-Dade",
        "start_date": datetime.date(2027, 4, 15),
        "end_date": datetime.date(2027, 4, 17),
        "sale_type": "deed",
        "status": "upcoming",
        "source_type": "statutory",
        "confidence_score": 1.0,
    }
    defaults.update(overrides)
    return Auction(**defaults)


class TestAuctionsToIcalBasic:
    def test_empty_list_returns_valid_calendar(self):
        result = auctions_to_ical([])
        cal = Calendar.from_ical(result)
        assert cal["PRODID"] == "-//TDC Auction Calendar//EN"
        assert cal["VERSION"] == "2.0"
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert events == []

    def test_single_auction_produces_vevent(self):
        auction = _make_auction()
        result = auctions_to_ical([auction])
        cal = Calendar.from_ical(result)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1

    def test_summary_format(self):
        auction = _make_auction(county="Miami-Dade", state="FL", sale_type="deed")
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert str(event["SUMMARY"]) == "Miami-Dade FL Tax Deed Sale"

    def test_dtstart_dtend_with_end_date(self):
        auction = _make_auction(
            start_date=datetime.date(2027, 4, 15),
            end_date=datetime.date(2027, 4, 17),
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert event["DTSTART"].dt == datetime.date(2027, 4, 15)
        assert event["DTEND"].dt == datetime.date(2027, 4, 17)

    def test_dtend_defaults_to_start_plus_one_when_no_end_date(self):
        auction = _make_auction(
            start_date=datetime.date(2027, 4, 15),
            end_date=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert event["DTEND"].dt == datetime.date(2027, 4, 16)

    def test_uid_is_deterministic(self):
        auction = _make_auction(
            state="FL", county="Miami-Dade",
            start_date=datetime.date(2027, 4, 15),
            sale_type="deed",
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert str(event["UID"]) == "FL-Miami-Dade-2027-04-15-deed@tdc-auction-calendar"
