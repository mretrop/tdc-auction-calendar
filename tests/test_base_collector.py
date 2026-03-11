"""Tests for BaseCollector abstract class and deduplication logic."""

import datetime

import pytest

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType


def _make_auction(
    state: str = "FL",
    county: str = "Miami-Dade",
    start_date: datetime.date = datetime.date(2026, 6, 1),
    sale_type: SaleType = SaleType.DEED,
    confidence: float = 0.5,
    vendor: str | None = None,
) -> Auction:
    return Auction(
        state=state,
        county=county,
        start_date=start_date,
        sale_type=sale_type,
        source_type=SourceType.STATUTORY,
        confidence_score=confidence,
        vendor=vendor,
    )


class ConcreteCollector(BaseCollector):
    """Minimal concrete subclass for testing."""

    async def collect(self) -> list[Auction]:
        return []

    def normalize(self, raw: dict) -> Auction:
        return _make_auction(**raw)


def test_cannot_instantiate_abc():
    """BaseCollector cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseCollector()


def test_concrete_subclass_instantiates():
    """A concrete subclass implementing all abstract methods can be created."""
    collector = ConcreteCollector()
    assert isinstance(collector, BaseCollector)


def test_deduplicate_no_duplicates():
    """With no duplicates, all auctions are returned."""
    collector = ConcreteCollector()
    auctions = [
        _make_auction(county="Miami-Dade"),
        _make_auction(county="Broward"),
        _make_auction(county="Palm Beach"),
    ]
    result = collector.deduplicate(auctions)
    assert len(result) == 3


def test_deduplicate_keeps_highest_confidence():
    """When duplicates exist, the one with highest confidence_score wins."""
    collector = ConcreteCollector()
    auctions = [
        _make_auction(confidence=0.4),
        _make_auction(confidence=0.8),
        _make_auction(confidence=0.6),
    ]
    result = collector.deduplicate(auctions)
    assert len(result) == 1
    assert result[0].confidence_score == 0.8


def test_deduplicate_equal_confidence_keeps_first():
    """When duplicates have equal confidence, the first encountered wins."""
    collector = ConcreteCollector()
    auctions = [
        _make_auction(confidence=0.5, vendor="RealAuction"),
        _make_auction(confidence=0.5, vendor="Bid4Assets"),
    ]
    result = collector.deduplicate(auctions)
    assert len(result) == 1
    assert result[0].vendor == "RealAuction"


def test_deduplicate_preserves_different_dedup_keys():
    """Auctions with different dedup keys are all preserved."""
    collector = ConcreteCollector()
    auctions = [
        _make_auction(state="FL", county="Miami-Dade", confidence=0.4),
        _make_auction(state="FL", county="Miami-Dade", confidence=0.8),
        _make_auction(state="TX", county="Harris", confidence=0.4),
        _make_auction(state="TX", county="Harris", confidence=0.6),
    ]
    result = collector.deduplicate(auctions)
    assert len(result) == 2
    by_state = {a.state: a for a in result}
    assert by_state["FL"].confidence_score == 0.8
    assert by_state["TX"].confidence_score == 0.6


def test_deduplicate_empty_list():
    """Deduplicating an empty list returns an empty list."""
    collector = ConcreteCollector()
    assert collector.deduplicate([]) == []
