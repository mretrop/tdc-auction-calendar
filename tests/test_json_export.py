"""Tests for JSON exporter."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

from tdc_auction_calendar.exporters.json_export import auctions_to_json
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


class TestAuctionsToJson:
    def test_empty_list_returns_empty_array(self):
        result = auctions_to_json([])
        assert json.loads(result) == []

    def test_round_trip_validates_against_pydantic(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_amount=Decimal("5000.00"),
            source_url="https://example.com/auction",
        )
        result = auctions_to_json([auction])
        parsed = json.loads(result)
        assert len(parsed) == 1
        restored = Auction(**parsed[0])
        assert restored.state == "FL"
        assert restored.start_date == datetime.date(2027, 4, 15)
        assert restored.deposit_amount == Decimal("5000.00")

    def test_compact_mode_no_whitespace(self):
        auction = _make_auction()
        result = auctions_to_json([auction], compact=True)
        assert "\n" not in result
        json.loads(result)

    def test_pretty_mode_has_indentation(self):
        auction = _make_auction()
        result = auctions_to_json([auction], compact=False)
        assert "\n" in result
        lines = result.split("\n")
        assert any(line.startswith("  ") for line in lines)

    def test_all_auction_fields_present(self):
        auction = _make_auction()
        result = auctions_to_json([auction])
        parsed = json.loads(result)[0]
        expected_fields = set(Auction.model_fields.keys())
        assert set(parsed.keys()) == expected_fields

    def test_multiple_auctions(self):
        a1 = _make_auction(state="FL")
        a2 = _make_auction(state="TX", county="Harris")
        result = auctions_to_json([a1, a2])
        parsed = json.loads(result)
        assert len(parsed) == 2
