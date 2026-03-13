"""Tests for the CLI interface."""

import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession
from typer.testing import CliRunner

from tdc_auction_calendar.cli import app
from tdc_auction_calendar.models import Base
from tdc_auction_calendar.models.auction import AuctionRow
from tdc_auction_calendar.models.health import CollectorError, CollectorHealthRow, RunReport
from tdc_auction_calendar.models.jurisdiction import CountyInfoRow, StateRulesRow

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
    def test_db_path_option_is_accepted(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        # Invoke a lightweight command with --db-path
        result = runner.invoke(app, ["--db-path", "sqlite:///test.db", "states"])
        # The command may fail (no DB) but the option should be accepted
        assert result.exit_code != 2  # exit 2 = Typer usage error


class TestExportStubs:
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


class TestExportIcal:
    def test_export_ical_no_db_exits_1(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'nope.db'}")
        result = runner.invoke(app, ["export", "ical"])
        assert result.exit_code == 1
        assert "Database not found" in result.output

    def test_export_ical_empty_db_produces_valid_ics(self, cli_db):
        result = runner.invoke(app, ["export", "ical"])
        assert result.exit_code == 0
        assert b"BEGIN:VCALENDAR" in result.output_bytes

    def test_export_ical_includes_auction(self, cli_db):
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=_future_date(),
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=1.0,
            ))
            session.commit()

        result = runner.invoke(app, ["export", "ical"])
        assert result.exit_code == 0
        assert b"Miami-Dade FL Tax Deed Sale" in result.output_bytes

    def test_export_ical_filters_by_state(self, cli_db):
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=_future_date(),
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=1.0,
            ))
            session.add(AuctionRow(
                state="TX", county="Harris",
                start_date=_future_date(days=400),
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=1.0,
            ))
            session.commit()

        result = runner.invoke(app, ["export", "ical", "--state", "FL"])
        assert b"Miami-Dade" in result.output_bytes
        assert b"Harris" not in result.output_bytes

    def test_export_ical_filters_by_sale_type(self, cli_db):
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=_future_date(),
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=1.0,
            ))
            session.add(AuctionRow(
                state="FL", county="Broward",
                start_date=_future_date(days=400),
                sale_type="lien", status="upcoming",
                source_type="statutory", confidence_score=1.0,
            ))
            session.commit()

        result = runner.invoke(app, ["export", "ical", "--sale-type", "lien"])
        assert b"Broward" in result.output_bytes
        assert b"Miami-Dade" not in result.output_bytes

    def test_export_ical_output_to_file(self, cli_db, tmp_path):
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=_future_date(),
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=1.0,
            ))
            session.commit()

        out_file = tmp_path / "auctions.ics"
        result = runner.invoke(app, ["export", "ical", "--output", str(out_file)])
        assert result.exit_code == 0
        content = out_file.read_bytes()
        assert b"BEGIN:VCALENDAR" in content
        assert b"Miami-Dade" in content

    def test_export_ical_invalid_date_format_exits_1(self, cli_db):
        result = runner.invoke(app, ["export", "ical", "--from-date", "not-a-date"])
        assert result.exit_code == 1
        assert "Invalid date format" in result.output

    def test_export_ical_from_date_includes_past(self, cli_db):
        past = _past_date(days=10)
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=past,
                sale_type="deed", status="completed",
                source_type="statutory", confidence_score=1.0,
            ))
            session.commit()

        # Without --from-date, the past auction is excluded
        result = runner.invoke(app, ["export", "ical"])
        assert b"Miami-Dade" not in result.output_bytes

        # With --from-date before the auction, it appears
        result = runner.invoke(app, ["export", "ical", "--from-date", str(past - datetime.timedelta(days=1))])
        assert b"Miami-Dade" in result.output_bytes

    def test_export_ical_to_date_limits_range(self, cli_db):
        near = _future_date(days=30)
        far = _future_date(days=400)
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=near,
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=1.0,
            ))
            session.add(AuctionRow(
                state="TX", county="Harris",
                start_date=far,
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=1.0,
            ))
            session.commit()

        cutoff = near + datetime.timedelta(days=5)
        result = runner.invoke(app, ["export", "ical", "--to-date", str(cutoff)])
        assert b"Miami-Dade" in result.output_bytes
        assert b"Harris" not in result.output_bytes


class TestSyncStub:
    def test_sync_supabase_stub(self):
        result = runner.invoke(app, ["sync", "supabase"])
        assert result.exit_code == 1
        assert "Not yet implemented" in result.output


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

    @patch("tdc_auction_calendar.cli.run_and_persist", new_callable=AsyncMock)
    @patch("tdc_auction_calendar.cli.get_session")
    @patch("tdc_auction_calendar.cli._ensure_tables")
    def test_collect_unexpected_exception_exits_1(self, mock_tables, mock_session, mock_run):
        mock_run.side_effect = RuntimeError("connection refused")
        result = runner.invoke(app, ["collect", "--collectors", "statutory"])
        assert result.exit_code == 1
        assert "Collection failed" in result.output


def _future_date(days=365):
    """Return a future date that won't expire in tests."""
    return datetime.date.today() + datetime.timedelta(days=days)


def _past_date(days=30):
    """Return a past date for testing --from-date override."""
    return datetime.date.today() - datetime.timedelta(days=days)


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

    def test_list_from_date_overrides_today_default(self, cli_db):
        past = _past_date(days=10)
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=past,
                sale_type="deed", status="completed",
                source_type="statutory", confidence_score=0.5,
            ))
            session.commit()

        # Without --from-date, the past auction is excluded (default: today)
        result = runner.invoke(app, ["list"])
        assert "No auctions found" in result.output

        # With --from-date before the auction, it appears
        result = runner.invoke(app, ["list", "--from-date", str(past - datetime.timedelta(days=1))])
        assert "Miami-Dade" in result.output

    def test_list_to_date_limits_range(self, cli_db):
        near = _future_date(days=30)
        far = _future_date(days=400)
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=near,
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=0.5,
            ))
            session.add(AuctionRow(
                state="TX", county="Harris",
                start_date=far,
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=0.5,
            ))
            session.commit()

        cutoff = near + datetime.timedelta(days=5)
        result = runner.invoke(app, ["list", "--to-date", str(cutoff)])
        assert "Miami-Dade" in result.output
        assert "Harris" not in result.output

    def test_list_respects_limit(self, cli_db):
        with SASession(cli_db) as session:
            for i in range(3):
                session.add(AuctionRow(
                    state="FL", county=f"County-{i}",
                    start_date=_future_date(days=30 + i),
                    sale_type="deed", status="upcoming",
                    source_type="statutory", confidence_score=0.5,
                ))
            session.commit()

        result = runner.invoke(app, ["list", "--limit", "2"])
        assert result.exit_code == 0
        assert "County-0" in result.output
        assert "County-1" in result.output
        assert "County-2" not in result.output

    def test_list_invalid_date_format_exits_1(self, cli_db):
        result = runner.invoke(app, ["list", "--from-date", "not-a-date"])
        assert result.exit_code == 1
        assert "Invalid date format" in result.output


class TestStatus:
    def test_status_no_db_exits_1(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'nope.db'}")
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "Database not found" in result.output

    def test_status_shows_stats(self, cli_db):
        with SASession(cli_db) as session:
            session.add(AuctionRow(
                state="FL", county="Miami-Dade",
                start_date=_future_date(),
                sale_type="deed", status="upcoming",
                source_type="statutory", confidence_score=0.4,
            ))
            session.commit()

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "1" in result.output  # total count
        assert "FL" in result.output

    def test_status_shows_collector_health(self, cli_db):
        now = datetime.datetime.now(datetime.timezone.utc)
        with SASession(cli_db) as session:
            session.add(CollectorHealthRow(
                collector_name="statutory",
                last_run=now,
                last_success=now,
                records_collected=100,
            ))
            session.commit()

        result = runner.invoke(app, ["status"])
        assert "statutory" in result.output
        assert "100" in result.output

    def test_status_empty_db(self, cli_db):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Total auctions: 0" in result.output
        assert "No collector health data" in result.output


class TestStates:
    def test_states_no_db_exits_1(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'nope.db'}")
        result = runner.invoke(app, ["states"])
        assert result.exit_code == 1

    def test_states_shows_data(self, cli_db):
        with SASession(cli_db) as session:
            session.add(StateRulesRow(
                state="FL", sale_type="deed",
                typical_months=[3, 4, 5],
                redemption_period_months=None,
            ))
            session.commit()

        result = runner.invoke(app, ["states"])
        assert result.exit_code == 0
        assert "FL" in result.output
        assert "deed" in result.output
        assert "Mar" in result.output

    def test_states_empty_prints_message(self, cli_db):
        result = runner.invoke(app, ["states"])
        assert "No states found" in result.output

    def test_states_shows_redemption_period(self, cli_db):
        with SASession(cli_db) as session:
            session.add(StateRulesRow(
                state="TX", sale_type="deed",
                typical_months=[1, 2],
                redemption_period_months=6,
            ))
            session.commit()

        result = runner.invoke(app, ["states"])
        assert "TX" in result.output
        assert "6" in result.output


class TestCounties:
    def test_counties_no_db_exits_1(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'nope.db'}")
        result = runner.invoke(app, ["counties"])
        assert result.exit_code == 1

    def test_counties_shows_data(self, cli_db):
        with SASession(cli_db) as session:
            session.add(CountyInfoRow(
                fips_code="12086", state="FL", county_name="Miami-Dade",
                timezone="America/New_York", priority="high",
                known_auction_vendor="RealAuction",
                tax_sale_page_url="https://example.com/auction",
            ))
            session.commit()

        result = runner.invoke(app, ["counties"])
        assert result.exit_code == 0
        assert "Miami-Dade" in result.output
        assert "RealAuction" in result.output

    def test_counties_filters_by_state(self, cli_db):
        with SASession(cli_db) as session:
            session.add(CountyInfoRow(
                fips_code="12086", state="FL", county_name="Miami-Dade",
                timezone="America/New_York", priority="high",
            ))
            session.add(CountyInfoRow(
                fips_code="48201", state="TX", county_name="Harris",
                timezone="America/Chicago", priority="medium",
            ))
            session.commit()

        result = runner.invoke(app, ["counties", "--state", "FL"])
        assert "Miami-Dade" in result.output
        assert "Harris" not in result.output

    def test_counties_empty_prints_message(self, cli_db):
        result = runner.invoke(app, ["counties"])
        assert "No counties found" in result.output

    def test_counties_null_vendor_shows_dash(self, cli_db):
        with SASession(cli_db) as session:
            session.add(CountyInfoRow(
                fips_code="12086", state="FL", county_name="Miami-Dade",
                timezone="America/New_York", priority="high",
                known_auction_vendor=None,
                tax_sale_page_url=None,
            ))
            session.commit()

        result = runner.invoke(app, ["counties"])
        assert result.exit_code == 0
        assert "Miami-Dade" in result.output
