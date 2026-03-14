"""Tests for Supabase sync module."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import AuctionStatus, SaleType, SourceType
from tdc_auction_calendar.sync.supabase_sync import SyncResult, sync_to_supabase


def _make_auction(**overrides) -> Auction:
    defaults = {
        "state": "FL",
        "county": "Miami-Dade",
        "start_date": datetime.date(2027, 3, 15),
        "sale_type": SaleType.DEED,
        "status": AuctionStatus.UPCOMING,
        "source_type": SourceType.STATUTORY,
        "confidence_score": 0.95,
    }
    defaults.update(overrides)
    return Auction(**defaults)


class TestSyncResult:
    def test_fields(self):
        r = SyncResult(synced=10, failed=2)
        assert r.synced == 10
        assert r.failed == 2


class TestSyncToSupabase:
    @patch("tdc_auction_calendar.sync.supabase_sync.query_auctions")
    @patch("tdc_auction_calendar.sync.supabase_sync.create_client")
    def test_upserts_auctions(self, mock_create, mock_query):
        auctions = [_make_auction(), _make_auction(county="Broward")]
        mock_query.return_value = auctions

        mock_table = MagicMock()
        mock_create.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = MagicMock(data=auctions)

        session = MagicMock()
        result = sync_to_supabase(session, "https://x.supabase.co", "key123")

        assert result.synced == 2
        assert result.failed == 0
        mock_table.upsert.assert_called_once()
        mock_create.assert_called_once_with("https://x.supabase.co", "key123")

    @patch("tdc_auction_calendar.sync.supabase_sync.query_auctions")
    @patch("tdc_auction_calendar.sync.supabase_sync.create_client")
    def test_payload_drops_id_field(self, mock_create, mock_query):
        mock_query.return_value = [_make_auction(id=42)]

        mock_table = MagicMock()
        mock_create.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = MagicMock(data=[{}])

        session = MagicMock()
        sync_to_supabase(session, "https://x.supabase.co", "key123")

        call_args = mock_table.upsert.call_args
        rows = call_args[0][0]
        for row in rows:
            assert "id" not in row

    @patch("tdc_auction_calendar.sync.supabase_sync.query_auctions")
    @patch("tdc_auction_calendar.sync.supabase_sync.create_client")
    def test_passes_filters_to_query(self, mock_create, mock_query):
        mock_query.return_value = []
        mock_create.return_value.table.return_value = MagicMock()

        session = MagicMock()
        sync_to_supabase(
            session, "https://x.supabase.co", "key123",
            states=["FL"], upcoming_only=True,
        )

        mock_query.assert_called_once_with(
            session,
            states=["FL"],
            sale_type=None,
            from_date=None,
            to_date=None,
            upcoming_only=True,
        )

    @patch("tdc_auction_calendar.sync.supabase_sync.query_auctions")
    @patch("tdc_auction_calendar.sync.supabase_sync.create_client")
    def test_empty_auction_list(self, mock_create, mock_query):
        mock_query.return_value = []

        session = MagicMock()
        result = sync_to_supabase(session, "https://x.supabase.co", "key123")

        assert result.synced == 0
        assert result.failed == 0
        mock_create.return_value.table.return_value.upsert.assert_not_called()

    @patch("tdc_auction_calendar.sync.supabase_sync.query_auctions")
    @patch("tdc_auction_calendar.sync.supabase_sync.create_client")
    def test_batch_chunking(self, mock_create, mock_query):
        # 250 auctions should produce 3 batches (100 + 100 + 50)
        auctions = [
            _make_auction(county=f"County-{i}", start_date=datetime.date(2027, 1, 1) + datetime.timedelta(days=i))
            for i in range(250)
        ]
        mock_query.return_value = auctions

        mock_table = MagicMock()
        mock_create.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = MagicMock(data=[{}])

        session = MagicMock()
        result = sync_to_supabase(session, "https://x.supabase.co", "key123")

        assert mock_table.upsert.call_count == 3
        assert result.synced == 250

    @patch("tdc_auction_calendar.sync.supabase_sync.query_auctions")
    @patch("tdc_auction_calendar.sync.supabase_sync.create_client")
    def test_batch_error_continues(self, mock_create, mock_query):
        auctions = [
            _make_auction(county=f"County-{i}", start_date=datetime.date(2027, 1, 1) + datetime.timedelta(days=i))
            for i in range(150)
        ]
        mock_query.return_value = auctions

        mock_table = MagicMock()
        mock_create.return_value.table.return_value = mock_table
        # First batch succeeds, second fails
        mock_table.upsert.return_value.execute.side_effect = [
            MagicMock(data=[{}] * 100),
            Exception("Supabase error"),
        ]

        session = MagicMock()
        result = sync_to_supabase(session, "https://x.supabase.co", "key123")

        assert result.synced == 100
        assert result.failed == 50

    @patch("tdc_auction_calendar.sync.supabase_sync.query_auctions")
    @patch("tdc_auction_calendar.sync.supabase_sync.create_client")
    def test_on_conflict_uses_dedup_key(self, mock_create, mock_query):
        mock_query.return_value = [_make_auction()]

        mock_table = MagicMock()
        mock_create.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = MagicMock(data=[{}])

        session = MagicMock()
        sync_to_supabase(session, "https://x.supabase.co", "key123")

        call_kwargs = mock_table.upsert.call_args[1]
        assert call_kwargs["on_conflict"] == "state,county,start_date,sale_type"

    @patch("tdc_auction_calendar.sync.supabase_sync.query_auctions")
    @patch("tdc_auction_calendar.sync.supabase_sync.create_client")
    def test_first_batch_failure_aborts(self, mock_create, mock_query):
        auctions = [
            _make_auction(county=f"County-{i}", start_date=datetime.date(2027, 1, 1) + datetime.timedelta(days=i))
            for i in range(150)
        ]
        mock_query.return_value = auctions

        mock_table = MagicMock()
        mock_create.return_value.table.return_value = mock_table
        mock_table.upsert.return_value.execute.side_effect = Exception("auth error")

        session = MagicMock()
        with pytest.raises(RuntimeError, match="First batch failed"):
            sync_to_supabase(session, "https://x.supabase.co", "key123")

        # Should abort after first batch, not attempt remaining batches
        assert mock_table.upsert.call_count == 1
