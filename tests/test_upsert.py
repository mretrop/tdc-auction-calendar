"""Tests for auction upsert and health persistence."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from tdc_auction_calendar.db.upsert import (
    get_collector_health,
    save_collector_health,
    upsert_auctions,
)
from tdc_auction_calendar.models import Auction, AuctionRow, UpsertResult
from tdc_auction_calendar.models.health import CollectorHealth, CollectorHealthRow


def _make_auction(**overrides) -> Auction:
    """Build a valid Auction with sensible defaults."""
    defaults = {
        "state": "FL",
        "county": "Miami-Dade",
        "start_date": datetime.date(2027, 6, 1),
        "sale_type": "deed",
        "source_type": "public_notice",
        "confidence_score": 0.75,
    }
    defaults.update(overrides)
    return Auction(**defaults)


class TestUpsertAuctions:
    def test_insert_new_record(self, db_session):
        """New auction is inserted."""
        auction = _make_auction()
        result = upsert_auctions(db_session, [auction])

        assert result.new == 1
        assert result.updated == 0
        assert result.skipped == 0

        row = db_session.query(AuctionRow).one()
        assert row.state == "FL"
        assert row.county == "Miami-Dade"
        assert row.confidence_score == 0.75

    def test_update_higher_confidence(self, db_session):
        """Higher confidence auction replaces existing."""
        low = _make_auction(confidence_score=0.40, source_type="statutory")
        upsert_auctions(db_session, [low])

        high = _make_auction(
            confidence_score=0.85,
            source_type="state_agency",
            source_url="https://example.com",
        )
        result = upsert_auctions(db_session, [high])

        assert result.new == 0
        assert result.updated == 1
        assert result.skipped == 0

        row = db_session.query(AuctionRow).one()
        assert row.confidence_score == 0.85
        assert row.source_type == "state_agency"
        assert row.source_url == "https://example.com"

    def test_skip_equal_confidence(self, db_session):
        """Equal confidence auction is skipped."""
        first = _make_auction(confidence_score=0.75)
        upsert_auctions(db_session, [first])

        second = _make_auction(confidence_score=0.75, notes="duplicate")
        result = upsert_auctions(db_session, [second])

        assert result.skipped == 1
        assert result.updated == 0

    def test_skip_lower_confidence(self, db_session):
        """Lower confidence auction is skipped."""
        high = _make_auction(confidence_score=0.85)
        upsert_auctions(db_session, [high])

        low = _make_auction(confidence_score=0.40)
        result = upsert_auctions(db_session, [low])

        assert result.skipped == 1

        row = db_session.query(AuctionRow).one()
        assert row.confidence_score == 0.85

    def test_update_replaces_none_values(self, db_session):
        """Higher confidence replaces all fields including None overwrite."""
        original = _make_auction(
            confidence_score=0.40,
            source_url="https://example.com",
            notes="original",
        )
        upsert_auctions(db_session, [original])

        replacement = _make_auction(
            confidence_score=0.85,
            source_url=None,
            notes=None,
        )
        result = upsert_auctions(db_session, [replacement])

        assert result.updated == 1
        row = db_session.query(AuctionRow).one()
        assert row.source_url is None
        assert row.notes is None

    def test_batch_insert_multiple(self, db_session):
        """Multiple new auctions in one call."""
        auctions = [
            _make_auction(county="Miami-Dade"),
            _make_auction(county="Broward"),
            _make_auction(county="Palm Beach"),
        ]
        result = upsert_auctions(db_session, [auctions[0], auctions[1], auctions[2]])

        assert result.new == 3
        assert db_session.query(AuctionRow).count() == 3

    def test_mixed_operations(self, db_session):
        """Mix of inserts, updates, and skips in one call."""
        existing = _make_auction(county="Miami-Dade", confidence_score=0.75)
        upsert_auctions(db_session, [existing])

        batch = [
            _make_auction(county="Miami-Dade", confidence_score=0.85),  # update
            _make_auction(county="Broward", confidence_score=0.75),     # new
        ]
        result = upsert_auctions(db_session, batch)

        assert result.new == 1
        assert result.updated == 1

    def test_empty_list(self, db_session):
        """Empty auction list returns zero counts."""
        result = upsert_auctions(db_session, [])
        assert result == UpsertResult(new=0, updated=0, skipped=0)
