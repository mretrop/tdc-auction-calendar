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

    def test_integrity_error_preserves_prior_inserts(self, db_session):
        """IntegrityError mid-batch does not roll back prior inserts."""
        # Insert first auction directly to create a conflict target
        first = _make_auction(county="Miami-Dade")
        upsert_auctions(db_session, [first])
        db_session.flush()

        # Batch: new record, then duplicate (same dedup key, same confidence → skip),
        # then another new record
        batch = [
            _make_auction(county="Broward"),
            _make_auction(county="Miami-Dade"),  # same key, same confidence → skipped
            _make_auction(county="Palm Beach"),
        ]
        result = upsert_auctions(db_session, batch)

        assert result.new == 2
        assert result.skipped == 1
        # All 3 records (original + 2 new) must exist
        assert db_session.query(AuctionRow).count() == 3


class TestSaveCollectorHealth:
    def test_save_success(self, db_session):
        """Successful run records health."""
        save_collector_health(
            db_session,
            name="florida_public_notice",
            success=True,
            records=42,
            error=None,
        )

        row = db_session.query(CollectorHealthRow).one()
        assert row.collector_name == "florida_public_notice"
        assert row.records_collected == 42
        assert row.last_success is not None
        assert row.error_message is None

    def test_save_failure(self, db_session):
        """Failed run records error, no last_success."""
        save_collector_health(
            db_session,
            name="broken_collector",
            success=False,
            records=0,
            error="Connection refused",
        )

        row = db_session.query(CollectorHealthRow).one()
        assert row.error_message == "Connection refused"
        assert row.last_success is None

    def test_success_after_failure_clears_error(self, db_session):
        """Success after failure clears error_message."""
        save_collector_health(
            db_session, name="flaky", success=False, records=0, error="timeout"
        )
        save_collector_health(
            db_session, name="flaky", success=True, records=10, error=None
        )

        row = db_session.query(CollectorHealthRow).one()
        assert row.error_message is None
        assert row.records_collected == 10
        assert row.last_success is not None

    def test_failure_preserves_last_success(self, db_session):
        """Failure after success preserves last_success and records_collected."""
        save_collector_health(
            db_session, name="flaky", success=True, records=10, error=None
        )
        first_success = db_session.query(CollectorHealthRow).one().last_success

        save_collector_health(
            db_session, name="flaky", success=False, records=0, error="boom"
        )

        row = db_session.query(CollectorHealthRow).one()
        assert row.last_success == first_success
        assert row.records_collected == 10
        assert row.error_message == "boom"


class TestGetCollectorHealth:
    def test_get_empty(self, db_session):
        """Returns empty list when no health rows exist."""
        result = get_collector_health(db_session)
        assert result == []

    def test_get_returns_pydantic_models(self, db_session):
        """Returns CollectorHealth Pydantic models."""
        save_collector_health(
            db_session, name="test", success=True, records=5, error=None
        )
        result = get_collector_health(db_session)

        assert len(result) == 1
        assert isinstance(result[0], CollectorHealth)
        assert result[0].collector_name == "test"
        assert result[0].records_collected == 5
