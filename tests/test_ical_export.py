"""Tests for iCalendar exporter."""

from __future__ import annotations

import datetime
from decimal import Decimal

from icalendar import Calendar

from tdc_auction_calendar.exporters.filters import query_auctions
from tdc_auction_calendar.exporters.ical import auctions_to_ical
from tdc_auction_calendar.models.auction import Auction, AuctionRow


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

    def test_description_absent_when_all_fields_null(self):
        auction = _make_auction(
            registration_deadline=None,
            deposit_amount=None,
            deposit_deadline=None,
            property_count=None,
            source_url=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert "DESCRIPTION" not in event

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


class TestValarms:
    def test_registration_deadline_produces_two_alarms(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_deadline=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        assert len(alarms) == 2

    def test_registration_alarm_trigger_values(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_deadline=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        triggers = sorted([a["TRIGGER"].dt for a in alarms])
        expected_7d = datetime.datetime(2027, 3, 25, 0, 0, tzinfo=datetime.timezone.utc)
        expected_1d = datetime.datetime(2027, 3, 31, 0, 0, tzinfo=datetime.timezone.utc)
        assert triggers == [expected_7d, expected_1d]

    def test_deposit_deadline_produces_one_alarm(self):
        auction = _make_auction(
            registration_deadline=None,
            deposit_deadline=datetime.date(2027, 4, 10),
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        assert len(alarms) == 1

    def test_deposit_alarm_trigger_value(self):
        auction = _make_auction(
            registration_deadline=None,
            deposit_deadline=datetime.date(2027, 4, 10),
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarm = [c for c in event.walk() if c.name == "VALARM"][0]
        expected = datetime.datetime(2027, 4, 9, 0, 0, tzinfo=datetime.timezone.utc)
        assert alarm["TRIGGER"].dt == expected

    def test_both_deadlines_produce_three_alarms(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_deadline=datetime.date(2027, 4, 10),
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        assert len(alarms) == 3

    def test_no_deadlines_no_alarms(self):
        auction = _make_auction(
            registration_deadline=None,
            deposit_deadline=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        assert alarms == []

    def test_alarm_action_is_display(self):
        auction = _make_auction(registration_deadline=datetime.date(2027, 4, 1))
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        for alarm in alarms:
            assert str(alarm["ACTION"]) == "DISPLAY"


def _future(days=365):
    return datetime.date.today() + datetime.timedelta(days=days)


def _past(days=30):
    return datetime.date.today() - datetime.timedelta(days=days)


def _insert_auction(session, **overrides):
    """Insert an AuctionRow with defaults."""
    defaults = {
        "state": "FL",
        "county": "Miami-Dade",
        "start_date": _future(),
        "sale_type": "deed",
        "status": "upcoming",
        "source_type": "statutory",
        "confidence_score": 1.0,
    }
    defaults.update(overrides)
    session.add(AuctionRow(**defaults))
    session.commit()


class TestQueryAuctions:
    def test_returns_future_auctions_by_default(self, db_session):
        _insert_auction(db_session, start_date=_future())
        _insert_auction(db_session, county="Broward", start_date=_past())
        result = query_auctions(db_session)
        assert len(result) == 1
        assert result[0].county == "Miami-Dade"

    def test_filter_by_single_state(self, db_session):
        _insert_auction(db_session, state="FL")
        _insert_auction(db_session, state="TX", county="Harris")
        result = query_auctions(db_session, states=["FL"])
        assert len(result) == 1
        assert result[0].state == "FL"

    def test_filter_by_state_is_case_insensitive(self, db_session):
        _insert_auction(db_session, state="FL")
        result = query_auctions(db_session, states=["fl"])
        assert len(result) == 1
        assert result[0].state == "FL"

    def test_filter_by_multiple_states(self, db_session):
        _insert_auction(db_session, state="FL")
        _insert_auction(db_session, state="TX", county="Harris")
        _insert_auction(db_session, state="GA", county="Fulton", start_date=_future(days=400))
        result = query_auctions(db_session, states=["FL", "TX"])
        assert len(result) == 2
        assert {a.state for a in result} == {"FL", "TX"}

    def test_filter_by_sale_type(self, db_session):
        _insert_auction(db_session, sale_type="deed")
        _insert_auction(db_session, county="Broward", sale_type="lien")
        result = query_auctions(db_session, sale_type="lien")
        assert len(result) == 1
        assert result[0].sale_type == "lien"

    def test_filter_by_date_range(self, db_session):
        near = _future(days=30)
        far = _future(days=400)
        _insert_auction(db_session, start_date=near)
        _insert_auction(db_session, county="Broward", start_date=far)
        cutoff = near + datetime.timedelta(days=5)
        result = query_auctions(db_session, from_date=near, to_date=cutoff)
        assert len(result) == 1
        assert result[0].county == "Miami-Dade"

    def test_to_date_none_means_no_upper_bound(self, db_session):
        _insert_auction(db_session, start_date=_future(days=1000))
        result = query_auctions(db_session, from_date=datetime.date.today())
        assert len(result) == 1

    def test_returns_pydantic_models(self, db_session):
        _insert_auction(db_session)
        result = query_auctions(db_session)
        assert len(result) == 1
        assert isinstance(result[0], Auction)

    def test_ordered_by_start_date(self, db_session):
        _insert_auction(db_session, county="Later", start_date=_future(days=400))
        _insert_auction(db_session, county="Sooner", start_date=_future(days=30))
        result = query_auctions(db_session)
        assert result[0].county == "Sooner"
        assert result[1].county == "Later"


class TestRoundTrip:
    def test_full_round_trip(self):
        """Acceptance: output validates via icalendar parse round-trip."""
        auctions = [
            _make_auction(
                state="FL", county="Miami-Dade",
                start_date=datetime.date(2027, 4, 15),
                end_date=datetime.date(2027, 4, 17),
                sale_type="deed",
                registration_deadline=datetime.date(2027, 4, 1),
                deposit_deadline=datetime.date(2027, 4, 10),
                deposit_amount=Decimal("5000.00"),
                property_count=150,
                source_url="https://example.com/auction",
            ),
            _make_auction(
                state="TX", county="Harris",
                start_date=datetime.date(2027, 6, 1),
                end_date=None,
                sale_type="lien",
                registration_deadline=None,
                deposit_deadline=None,
                source_url=None,
            ),
        ]
        ical_bytes = auctions_to_ical(auctions)

        # Parse round-trip
        cal = Calendar.from_ical(ical_bytes)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 2

        # First event — full fields
        fl = next(e for e in events if "Miami-Dade" in str(e["SUMMARY"]))
        assert str(fl["SUMMARY"]) == "Miami-Dade FL Tax Deed Sale"
        assert fl["DTSTART"].dt == datetime.date(2027, 4, 15)
        assert fl["DTEND"].dt == datetime.date(2027, 4, 17)
        assert "URL" in fl
        alarms = [c for c in fl.walk() if c.name == "VALARM"]
        assert len(alarms) == 3  # 2 registration + 1 deposit

        # Second event — minimal fields
        tx = next(e for e in events if "Harris" in str(e["SUMMARY"]))
        assert tx["DTEND"].dt == datetime.date(2027, 6, 2)  # start + 1 day
        assert "URL" not in tx
        tx_alarms = [c for c in tx.walk() if c.name == "VALARM"]
        assert len(tx_alarms) == 0

    def test_multiple_auctions_same_fields(self):
        """Multiple events with unique UIDs."""
        a1 = _make_auction(state="FL", county="Miami-Dade", start_date=datetime.date(2027, 4, 15))
        a2 = _make_auction(state="FL", county="Broward", start_date=datetime.date(2027, 5, 1))
        cal = Calendar.from_ical(auctions_to_ical([a1, a2]))
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        uids = [str(e["UID"]) for e in events]
        assert len(set(uids)) == 2  # unique UIDs
