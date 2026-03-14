"""Tests for shared export query/filter layer."""

from __future__ import annotations

import datetime

from tdc_auction_calendar.exporters.filters import query_auctions
from tdc_auction_calendar.models.auction import Auction, AuctionRow


def _future(days=365):
    return datetime.date.today() + datetime.timedelta(days=days)


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


class TestUpcomingOnlyFilter:
    def test_upcoming_only_excludes_completed(self, db_session):
        _insert_auction(db_session, county="Active", status="upcoming")
        _insert_auction(db_session, county="Done", status="completed")
        result = query_auctions(db_session, upcoming_only=True)
        assert len(result) == 1
        assert result[0].county == "Active"

    def test_upcoming_only_false_returns_all(self, db_session):
        _insert_auction(db_session, county="Active", status="upcoming")
        _insert_auction(db_session, county="Done", status="completed")
        result = query_auctions(db_session, upcoming_only=False)
        assert len(result) == 2
