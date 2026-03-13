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


class TestDescriptionAndUrl:
    def test_description_with_all_fields(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_amount=Decimal("5000.00"),
            deposit_deadline=datetime.date(2027, 4, 10),
            property_count=150,
            source_url="https://example.com/auction",
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        desc = str(event["DESCRIPTION"])
        assert "Registration deadline: 2027-04-01" in desc
        assert "Deposit amount: $5,000.00" in desc
        assert "Deposit deadline: 2027-04-10" in desc
        assert "Properties: 150" in desc
        assert "Source: https://example.com/auction" in desc

    def test_description_omits_null_fields(self):
        auction = _make_auction(
            registration_deadline=None,
            deposit_amount=None,
            deposit_deadline=None,
            property_count=None,
            source_url=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        desc = str(event.get("DESCRIPTION", ""))
        assert "Registration" not in desc
        assert "Deposit" not in desc
        assert "Properties" not in desc
        assert "Source" not in desc

    def test_url_present_when_source_url_set(self):
        auction = _make_auction(source_url="https://example.com/auction")
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert str(event["URL"]) == "https://example.com/auction"

    def test_url_absent_when_source_url_null(self):
        auction = _make_auction(source_url=None)
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert "URL" not in event
