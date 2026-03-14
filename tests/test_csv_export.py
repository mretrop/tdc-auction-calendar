"""Tests for CSV exporter."""

from __future__ import annotations

import csv
import datetime
import io
from decimal import Decimal

from tdc_auction_calendar.exporters.csv_export import CSV_COLUMNS, auctions_to_csv
from tdc_auction_calendar.models.auction import Auction


def _make_auction(**overrides) -> Auction:
    """Build an Auction with sensible defaults."""
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


class TestAuctionsToCsv:
    def test_empty_list_returns_header_only(self):
        result = auctions_to_csv([])
        reader = csv.DictReader(io.StringIO(result))
        assert reader.fieldnames == list(CSV_COLUMNS)
        assert list(reader) == []

    def test_round_trip_through_dictreader(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_amount=Decimal("5000.00"),
            interest_rate=Decimal("18.00"),
            property_count=150,
            vendor="RealAuction",
            source_url="https://example.com/auction",
        )
        result = auctions_to_csv([auction])
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 1
        row = rows[0]
        assert row["state"] == "FL"
        assert row["county"] == "Miami-Dade"
        assert row["sale_type"] == "deed"
        assert row["start_date"] == "2027-04-15"
        assert row["end_date"] == "2027-04-17"
        assert row["registration_deadline"] == "2027-04-01"
        assert row["deposit_amount"] == "5000.00"
        assert row["interest_rate"] == "18.00"
        assert row["property_count"] == "150"
        assert row["vendor"] == "RealAuction"
        assert row["confidence_score"] == "1.0"
        assert row["source_url"] == "https://example.com/auction"

    def test_null_fields_are_empty_strings(self):
        auction = _make_auction(
            end_date=None,
            registration_deadline=None,
            deposit_amount=None,
            interest_rate=None,
            property_count=None,
            vendor=None,
            source_url=None,
        )
        result = auctions_to_csv([auction])
        reader = csv.DictReader(io.StringIO(result))
        row = next(reader)
        assert row["end_date"] == ""
        assert row["deposit_amount"] == ""
        assert row["vendor"] == ""

    def test_multiple_auctions(self):
        a1 = _make_auction(state="FL")
        a2 = _make_auction(state="TX", county="Harris")
        result = auctions_to_csv([a1, a2])
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["state"] == "FL"
        assert rows[1]["state"] == "TX"
