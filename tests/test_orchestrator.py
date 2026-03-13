"""Tests for collector orchestrator."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest

from tdc_auction_calendar.collectors.orchestrator import (
    COLLECTORS,
    cross_dedup,
    run_all,
)
from tdc_auction_calendar.models import Auction


def _make_auction(**overrides) -> Auction:
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


class TestCrossDedup:
    def test_keeps_highest_confidence(self):
        """Cross-dedup keeps highest confidence for same dedup key."""
        low = _make_auction(confidence_score=0.40, source_type="statutory")
        high = _make_auction(confidence_score=0.85, source_type="state_agency")

        result = cross_dedup([low, high])

        assert len(result) == 1
        assert result[0].confidence_score == 0.85

    def test_different_keys_kept(self):
        """Auctions with different dedup keys are all kept."""
        a = _make_auction(county="Miami-Dade")
        b = _make_auction(county="Broward")

        result = cross_dedup([a, b])
        assert len(result) == 2

    def test_empty_list(self):
        """Empty input returns empty output."""
        assert cross_dedup([]) == []

    def test_first_wins_on_tie(self):
        """Equal confidence: first encountered wins."""
        first = _make_auction(confidence_score=0.75, notes="first")
        second = _make_auction(confidence_score=0.75, notes="second")

        result = cross_dedup([first, second])

        assert len(result) == 1
        assert result[0].notes == "first"
