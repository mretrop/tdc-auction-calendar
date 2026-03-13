"""Tests for health and orchestrator data models."""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.models.health import (
    CollectorError,
    CollectorHealth,
    CollectorHealthRow,
    RunReport,
    UpsertResult,
)


class TestCollectorHealth:
    def test_collector_health_from_orm(self, db_session):
        """CollectorHealthRow round-trips to CollectorHealth Pydantic model."""
        row = CollectorHealthRow(
            collector_name="florida_public_notice",
            last_run=datetime.datetime(2026, 3, 12, tzinfo=datetime.timezone.utc),
            last_success=datetime.datetime(2026, 3, 12, tzinfo=datetime.timezone.utc),
            records_collected=42,
            error_message=None,
        )
        db_session.add(row)
        db_session.flush()

        health = CollectorHealth(
            collector_name=row.collector_name,
            last_run=row.last_run,
            last_success=row.last_success,
            records_collected=row.records_collected,
            error_message=row.error_message,
        )
        assert health.collector_name == "florida_public_notice"
        assert health.records_collected == 42
        assert health.error_message is None

    def test_collector_health_with_error(self):
        """CollectorHealth accepts error state."""
        health = CollectorHealth(
            collector_name="broken",
            last_run=datetime.datetime(2026, 3, 12, tzinfo=datetime.timezone.utc),
            last_success=None,
            records_collected=0,
            error_message="Connection refused",
        )
        assert health.error_message == "Connection refused"
        assert health.last_success is None


class TestRunReport:
    def test_run_report_defaults(self):
        """RunReport initializes DB counts to zero."""
        report = RunReport(
            total_records=10,
            collectors_succeeded=["a"],
            collectors_failed=[],
            duration_seconds=1.5,
        )
        assert report.new_records == 0
        assert report.updated_records == 0
        assert report.skipped_records == 0
        assert report.per_collector_counts == {}

    def test_run_report_with_failures(self):
        """RunReport holds CollectorError list."""
        err = CollectorError(
            collector_name="broken", error="timeout", error_type="TimeoutError"
        )
        report = RunReport(
            total_records=0,
            collectors_succeeded=[],
            collectors_failed=[err],
            duration_seconds=0.5,
        )
        assert len(report.collectors_failed) == 1
        assert report.collectors_failed[0].error_type == "TimeoutError"


class TestUpsertResult:
    def test_upsert_result(self):
        result = UpsertResult(new=5, updated=3, skipped=2)
        assert result.new == 5
        assert result.updated == 3
        assert result.skipped == 2
