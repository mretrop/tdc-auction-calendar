"""Tests for the CLI interface."""

import pytest
from typer.testing import CliRunner

from tdc_auction_calendar.cli import app

runner = CliRunner()


class TestHelp:
    def test_help_shows_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ("collect", "list", "status", "states", "counties", "export", "sync"):
            assert cmd in result.output

    def test_help_shows_db_path_option(self):
        result = runner.invoke(app, ["--help"])
        assert "--db-path" in result.output


class TestDbPath:
    def test_db_path_sets_env_var(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        # Invoke a lightweight command with --db-path
        result = runner.invoke(app, ["--db-path", "sqlite:///test.db", "states"])
        # The command may fail (no DB) but the option should be accepted
        assert result.exit_code != 2  # exit 2 = Typer usage error


class TestExportStubs:
    def test_export_ical_stub(self):
        result = runner.invoke(app, ["export", "ical"])
        assert result.exit_code == 1
        assert "Not yet implemented" in result.output

    def test_export_csv_stub(self):
        result = runner.invoke(app, ["export", "csv"])
        assert result.exit_code == 1
        assert "Not yet implemented" in result.output

    def test_export_json_stub(self):
        result = runner.invoke(app, ["export", "json"])
        assert result.exit_code == 1
        assert "Not yet implemented" in result.output

    def test_export_rss_stub(self):
        result = runner.invoke(app, ["export", "rss"])
        assert result.exit_code == 1
        assert "Not yet implemented" in result.output


class TestSyncStub:
    def test_sync_supabase_stub(self):
        result = runner.invoke(app, ["sync", "supabase"])
        assert result.exit_code == 1
        assert "Not yet implemented" in result.output


from unittest.mock import AsyncMock, patch

from tdc_auction_calendar.models.health import CollectorError, RunReport


def _make_report(**overrides) -> RunReport:
    defaults = {
        "total_records": 10,
        "new_records": 8,
        "updated_records": 2,
        "skipped_records": 0,
        "collectors_succeeded": ["statutory"],
        "collectors_failed": [],
        "per_collector_counts": {"statutory": 10},
        "duration_seconds": 1.5,
    }
    defaults.update(overrides)
    return RunReport(**defaults)


class TestCollect:
    @patch("tdc_auction_calendar.cli.run_and_persist", new_callable=AsyncMock)
    @patch("tdc_auction_calendar.cli.get_session")
    @patch("tdc_auction_calendar.cli._ensure_tables")
    def test_collect_shows_summary(self, mock_tables, mock_session, mock_run):
        mock_run.return_value = _make_report()
        result = runner.invoke(app, ["collect"])
        assert result.exit_code == 0
        assert "statutory" in result.output
        assert "10" in result.output

    @patch("tdc_auction_calendar.cli.run_and_persist", new_callable=AsyncMock)
    @patch("tdc_auction_calendar.cli.get_session")
    @patch("tdc_auction_calendar.cli._ensure_tables")
    def test_collect_passes_collector_filter(self, mock_tables, mock_session, mock_run):
        mock_run.return_value = _make_report()
        runner.invoke(app, ["collect", "--collectors", "statutory"])
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["collectors"] == ["statutory"]

    @patch("tdc_auction_calendar.cli.run_and_persist", new_callable=AsyncMock)
    @patch("tdc_auction_calendar.cli.get_session")
    @patch("tdc_auction_calendar.cli._ensure_tables")
    def test_collect_unknown_collector_exits_1(self, mock_tables, mock_session, mock_run):
        mock_run.side_effect = ValueError("Unknown collector names: ['bogus']")
        result = runner.invoke(app, ["collect", "--collectors", "bogus"])
        assert result.exit_code == 1
        assert "Unknown" in result.output or "bogus" in result.output

    @patch("tdc_auction_calendar.cli.run_and_persist", new_callable=AsyncMock)
    @patch("tdc_auction_calendar.cli.get_session")
    @patch("tdc_auction_calendar.cli._ensure_tables")
    def test_collect_all_fail_exits_1(self, mock_tables, mock_session, mock_run):
        mock_run.return_value = _make_report(
            total_records=0,
            new_records=0,
            collectors_succeeded=[],
            collectors_failed=[
                CollectorError(collector_name="statutory", error="boom", error_type="RuntimeError")
            ],
            per_collector_counts={},
        )
        result = runner.invoke(app, ["collect"])
        assert result.exit_code == 1

    @patch("tdc_auction_calendar.cli.run_and_persist", new_callable=AsyncMock)
    @patch("tdc_auction_calendar.cli.get_session")
    @patch("tdc_auction_calendar.cli._ensure_tables")
    def test_collect_partial_failure_exits_0(self, mock_tables, mock_session, mock_run):
        mock_run.return_value = _make_report(
            collectors_succeeded=["statutory"],
            collectors_failed=[
                CollectorError(collector_name="florida_public_notice", error="timeout", error_type="TimeoutError")
            ],
        )
        result = runner.invoke(app, ["collect"])
        assert result.exit_code == 0


import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from tdc_auction_calendar.models import Base
from tdc_auction_calendar.models.auction import AuctionRow


def _future_date(days=365):
    """Return a future date that won't expire in tests."""
    return datetime.date.today() + datetime.timedelta(days=days)


@pytest.fixture()
def cli_db(tmp_path, monkeypatch):
    """File-based SQLite DB for CLI integration tests.

    Unlike the in-memory db_engine fixture, this creates a real file
    so that the CLI's get_session() can connect to the same database.
    """
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("DATABASE_URL", url)
    yield engine
    engine.dispose()


class TestList:
    def test_list_no_db_exits_1(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'nope.db'}")
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 1
        assert "Database not found" in result.output

    def test_list_shows_auctions(self, cli_db):
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=_future_date(),
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=0.85,
            ))
            session.commit()

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "FL" in result.output
        assert "Miami-Dade" in result.output
        assert "85%" in result.output

    def test_list_empty_prints_message(self, cli_db):
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No auctions found" in result.output

    def test_list_filters_by_state(self, cli_db):
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=_future_date(),
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=0.4,
            ))
            session.add(AuctionRow(
                state="TX", county="Harris",
                start_date=_future_date(days=400),
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=0.4,
            ))
            session.commit()

        result = runner.invoke(app, ["list", "--state", "FL"])
        assert "FL" in result.output
        assert "TX" not in result.output

    def test_list_filters_by_sale_type(self, cli_db):
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=_future_date(),
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=0.4,
            ))
            session.add(AuctionRow(
                state="FL", county="Broward",
                start_date=_future_date(days=400),
                sale_type="lien", status="upcoming",
                source_type="statutory", confidence_score=0.4,
            ))
            session.commit()

        result = runner.invoke(app, ["list", "--sale-type", "deed"])
        assert "Miami-Dade" in result.output
        assert "Broward" not in result.output
