"""Tests for collector orchestrator."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

from tdc_auction_calendar.collectors.orchestrator import (
    COLLECTORS,
    cross_dedup,
    run_all,
    run_and_persist,
)
from tdc_auction_calendar.models.health import CollectorHealthRow
from tdc_auction_calendar.models import Auction
from tdc_auction_calendar.models import AuctionRow


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


from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.models.enums import SourceType


class _SuccessCollector(BaseCollector):
    """Mock collector that returns fixed auctions."""

    _auctions: list[Auction] = []

    @property
    def name(self) -> str:
        return "success_collector"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATUTORY

    async def _fetch(self) -> list[Auction]:
        return self._auctions

    def normalize(self, raw: dict) -> Auction:
        return Auction(**raw)


@pytest.fixture(autouse=True)
def _reset_mock_collectors():
    """Reset shared mock collector state between tests."""
    _SuccessCollector._auctions = []
    yield
    _SuccessCollector._auctions = []


class _FailCollector(BaseCollector):
    """Mock collector that always raises."""

    @property
    def name(self) -> str:
        return "fail_collector"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATUTORY

    async def _fetch(self) -> list[Auction]:
        raise ConnectionError("site down")

    def normalize(self, raw: dict) -> Auction:
        return Auction(**raw)


class TestRunAll:
    async def test_collects_from_all(self):
        """run_all returns auctions from all collectors."""
        _SuccessCollector._auctions = [
            _make_auction(county="Miami-Dade"),
        ]

        with patch.dict(
            "tdc_auction_calendar.collectors.orchestrator.COLLECTORS",
            {"success": _SuccessCollector},
            clear=True,
        ):
            auctions, report = await run_all()

        assert len(auctions) == 1
        assert report.total_records == 1
        assert report.collectors_succeeded == ["success"]
        assert report.collectors_failed == []

    async def test_failure_isolation(self):
        """One collector failure does not stop others."""
        _SuccessCollector._auctions = [
            _make_auction(county="Broward"),
        ]

        with patch.dict(
            "tdc_auction_calendar.collectors.orchestrator.COLLECTORS",
            {"success": _SuccessCollector, "fail": _FailCollector},
            clear=True,
        ):
            auctions, report = await run_all()

        assert len(auctions) == 1
        assert "success" in report.collectors_succeeded
        assert len(report.collectors_failed) == 1
        assert report.collectors_failed[0].collector_name == "fail"
        assert report.collectors_failed[0].error_type == "ConnectionError"

    async def test_cross_dedup_applied(self):
        """Cross-collector dedup keeps highest confidence."""
        _SuccessCollector._auctions = [
            _make_auction(confidence_score=0.40, source_type="statutory"),
            _make_auction(confidence_score=0.85, source_type="state_agency"),
        ]

        with patch.dict(
            "tdc_auction_calendar.collectors.orchestrator.COLLECTORS",
            {"success": _SuccessCollector},
            clear=True,
        ):
            auctions, report = await run_all()

        assert len(auctions) == 1
        assert auctions[0].confidence_score == 0.85

    async def test_filter_by_name(self):
        """run_all filters to requested collector names."""
        _SuccessCollector._auctions = [_make_auction()]

        with patch.dict(
            "tdc_auction_calendar.collectors.orchestrator.COLLECTORS",
            {"a": _SuccessCollector, "b": _SuccessCollector},
            clear=True,
        ):
            auctions, report = await run_all(collectors=["a"])

        assert report.collectors_succeeded == ["a"]

    async def test_unknown_name_raises(self):
        """Unknown collector name raises ValueError."""
        with patch.dict(
            "tdc_auction_calendar.collectors.orchestrator.COLLECTORS",
            {"a": _SuccessCollector},
            clear=True,
        ):
            with pytest.raises(ValueError, match="Unknown collector"):
                await run_all(collectors=["nonexistent"])

    async def test_report_duration(self):
        """RunReport includes positive duration_seconds."""
        _SuccessCollector._auctions = []

        with patch.dict(
            "tdc_auction_calendar.collectors.orchestrator.COLLECTORS",
            {"a": _SuccessCollector},
            clear=True,
        ):
            _, report = await run_all()

        assert report.duration_seconds >= 0


class TestRunAndPersist:
    async def test_persists_auctions(self, db_session):
        """run_and_persist writes auctions to DB."""
        _SuccessCollector._auctions = [_make_auction()]

        with patch.dict(
            "tdc_auction_calendar.collectors.orchestrator.COLLECTORS",
            {"success": _SuccessCollector},
            clear=True,
        ):
            report = await run_and_persist(db_session)

        assert report.new_records == 1
        assert db_session.query(AuctionRow).count() == 1

    async def test_saves_health_on_success(self, db_session):
        """run_and_persist records health for successful collectors."""
        _SuccessCollector._auctions = [_make_auction()]

        with patch.dict(
            "tdc_auction_calendar.collectors.orchestrator.COLLECTORS",
            {"success": _SuccessCollector},
            clear=True,
        ):
            await run_and_persist(db_session)

        health = db_session.query(CollectorHealthRow).filter_by(
            collector_name="success"
        ).one()
        assert health.records_collected == 1
        assert health.error_message is None

    async def test_saves_health_on_failure(self, db_session):
        """run_and_persist records health for failed collectors."""
        with patch.dict(
            "tdc_auction_calendar.collectors.orchestrator.COLLECTORS",
            {"fail": _FailCollector},
            clear=True,
        ):
            report = await run_and_persist(db_session)

        assert len(report.collectors_failed) == 1
        health = db_session.query(CollectorHealthRow).filter_by(
            collector_name="fail"
        ).one()
        assert health.error_message is not None

    async def test_report_includes_upsert_counts(self, db_session):
        """run_and_persist populates new/updated/skipped on report."""
        _SuccessCollector._auctions = [
            _make_auction(county="Miami-Dade"),
            _make_auction(county="Broward"),
        ]

        with patch.dict(
            "tdc_auction_calendar.collectors.orchestrator.COLLECTORS",
            {"success": _SuccessCollector},
            clear=True,
        ):
            report = await run_and_persist(db_session)

        assert report.new_records == 2
        assert report.total_records == 2


class TestRegistry:
    def test_registry_has_12_collectors(self):
        """Registry contains all 12 collectors."""
        assert len(COLLECTORS) == 12

    def test_registry_keys_match_collector_names(self):
        """Registry keys match each collector's .name property."""
        for key, cls in COLLECTORS.items():
            instance = cls()
            assert key == instance.name, f"Registry key {key!r} != {cls.__name__}.name {instance.name!r}"
