# Supabase Sync Command Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CLI command that upserts local auction data to a Supabase `auctions` table.

**Architecture:** New `sync/supabase_sync.py` module with a single `sync_to_supabase()` function that queries local auctions via existing `query_auctions()`, converts them to dicts, and upserts to Supabase in batches of 100. The existing CLI stub at `cli.py:219` gets replaced with a real command wired to the sync module.

**Tech Stack:** supabase-py 2.x, existing SQLAlchemy/Pydantic models, Typer CLI

---

## Chunk 1: Sync Module + Tests

### Task 1: Create sync module with SyncResult and sync_to_supabase

**Files:**
- Create: `src/tdc_auction_calendar/sync/__init__.py`
- Create: `src/tdc_auction_calendar/sync/supabase_sync.py`
- Create: `tests/test_supabase_sync.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_supabase_sync.py`:

```python
"""Tests for Supabase sync module."""

import datetime
from unittest.mock import MagicMock, patch

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

    @patch("tdc_auction_calendar.sync.supabase_sync.query_auctions")
    @patch("tdc_auction_calendar.sync.supabase_sync.create_client")
    def test_payload_drops_id_field(self, mock_create, mock_query):
        mock_query.return_value = [_make_auction()]

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_supabase_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tdc_auction_calendar.sync'`

- [ ] **Step 3: Create the sync package and implement**

Create `src/tdc_auction_calendar/sync/__init__.py` (empty).

Create `src/tdc_auction_calendar/sync/supabase_sync.py`:

```python
"""Sync auction data to Supabase."""

from __future__ import annotations

import datetime
from typing import NamedTuple

import structlog
from sqlalchemy.orm import Session
from supabase import create_client

from tdc_auction_calendar.exporters.filters import query_auctions
from tdc_auction_calendar.models.enums import SaleType

logger = structlog.get_logger()

BATCH_SIZE = 100


class SyncResult(NamedTuple):
    synced: int
    failed: int


def sync_to_supabase(
    session: Session,
    supabase_url: str,
    service_role_key: str,
    *,
    states: list[str] | None = None,
    sale_type: SaleType | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
    upcoming_only: bool = False,
) -> SyncResult:
    """Query local auctions and upsert them to Supabase."""
    auctions = query_auctions(
        session,
        states=states,
        sale_type=sale_type,
        from_date=from_date,
        to_date=to_date,
        upcoming_only=upcoming_only,
    )

    if not auctions:
        logger.info("no auctions to sync")
        return SyncResult(synced=0, failed=0)

    client = create_client(supabase_url, service_role_key)
    table = client.table("auctions")

    rows = []
    for auction in auctions:
        row = auction.model_dump(mode="json")
        row.pop("id", None)
        rows.append(row)

    synced = 0
    failed = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        try:
            table.upsert(
                batch,
                on_conflict="state,county,start_date,sale_type",
            ).execute()
            synced += len(batch)
            logger.info("batch synced", batch_size=len(batch), total_synced=synced)
        except Exception:
            failed += len(batch)
            logger.exception("batch upsert failed", batch_start=i, batch_size=len(batch))

    return SyncResult(synced=synced, failed=failed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_supabase_sync.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/sync/ tests/test_supabase_sync.py
git commit -m "feat: Supabase sync module with batched upsert (issue #22)"
```

---

## Chunk 2: CLI Integration + Env Var Update

### Task 2: Wire sync command into CLI

**Files:**
- Modify: `src/tdc_auction_calendar/cli.py:219-223`
- Modify: `tests/test_cli.py:189-193`

- [ ] **Step 1: Update the CLI test for sync supabase**

In `tests/test_cli.py`, replace `TestSyncStub` with:

```python
class TestSyncSupabase:
    def test_sync_supabase_missing_env_vars(self, cli_db, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        result = runner.invoke(app, ["sync", "supabase"])
        assert result.exit_code == 1
        assert "SUPABASE_URL" in result.output

    @patch("tdc_auction_calendar.cli.sync_to_supabase")
    def test_sync_supabase_success(self, mock_sync, cli_db, monkeypatch):
        from tdc_auction_calendar.sync.supabase_sync import SyncResult
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "key123")
        mock_sync.return_value = SyncResult(synced=5, failed=0)

        result = runner.invoke(app, ["sync", "supabase"])
        assert result.exit_code == 0
        assert "5" in result.output

    @patch("tdc_auction_calendar.cli.sync_to_supabase")
    def test_sync_supabase_with_filters(self, mock_sync, cli_db, monkeypatch):
        from tdc_auction_calendar.sync.supabase_sync import SyncResult
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "key123")
        mock_sync.return_value = SyncResult(synced=2, failed=0)

        result = runner.invoke(app, ["sync", "supabase", "--state", "FL", "--upcoming-only"])
        assert result.exit_code == 0
        mock_sync.assert_called_once()
        call_kwargs = mock_sync.call_args[1]
        assert call_kwargs["states"] == ["FL"]
        assert call_kwargs["upcoming_only"] is True

    @patch("tdc_auction_calendar.cli.sync_to_supabase")
    def test_sync_supabase_with_failures(self, mock_sync, cli_db, monkeypatch):
        from tdc_auction_calendar.sync.supabase_sync import SyncResult
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "key123")
        mock_sync.return_value = SyncResult(synced=80, failed=20)

        result = runner.invoke(app, ["sync", "supabase"])
        assert result.exit_code == 1
        assert "80" in result.output
        assert "20" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestSyncSupabase -v`
Expected: FAIL — stub still returns "Not yet implemented"

- [ ] **Step 3: Replace the CLI stub**

In `cli.py`, replace the `sync_supabase` stub (lines 219-223) with:

```python
@sync_app.command("supabase")
def sync_supabase(
    state: list[str] | None = typer.Option(None, "--state", help="Filter by state code (repeatable)"),
    sale_type: SaleType | None = typer.Option(None, "--sale-type", help="Filter by sale type"),
    from_date: str | None = typer.Option(None, "--from-date", help="Start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, "--to-date", help="End date (YYYY-MM-DD)"),
    upcoming_only: bool = typer.Option(False, "--upcoming-only", help="Only include upcoming auctions"),
) -> None:
    """Upsert auction data to Supabase."""
    from tdc_auction_calendar.sync.supabase_sync import sync_to_supabase

    supabase_url = os.environ.get("SUPABASE_URL")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_role_key:
        console.print(
            "[red]Missing environment variables.[/red] "
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
        raise typer.Exit(1)

    if not _check_db_exists():
        console.print("[red]Database not found.[/red] Run `tdc-auction-calendar collect` first.")
        raise typer.Exit(1)

    from_parsed, to_parsed = _parse_dates(from_date, to_date)

    session = get_session()
    try:
        result = sync_to_supabase(
            session,
            supabase_url,
            service_role_key,
            states=state,
            sale_type=sale_type,
            from_date=from_parsed,
            to_date=to_parsed,
            upcoming_only=upcoming_only,
        )
    except Exception as exc:
        console.print(f"[red]Sync failed:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        session.close()

    console.print(f"Synced {result.synced} auction(s) to Supabase.")
    if result.failed:
        console.print(f"[yellow]{result.failed} record(s) failed.[/yellow]")
        raise typer.Exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::TestSyncSupabase -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/cli.py tests/test_cli.py
git commit -m "feat: wire Supabase sync CLI command (issue #22)"
```

### Task 3: Update .env.example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Update env var name and comment**

In `.env.example`, replace:
```
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```
with:
```
# Supabase (service role key bypasses RLS — required for sync writes)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "chore: rename SUPABASE_KEY to SUPABASE_SERVICE_ROLE_KEY"
```

### Task 4: Run full test suite

- [ ] **Step 1: Run all tests**

Run: `uv run pytest`
Expected: all pass, no regressions

- [ ] **Step 2: Check coverage on sync module**

Run: `uv run pytest tests/test_supabase_sync.py tests/test_cli.py --cov=tdc_auction_calendar.sync --cov-report=term-missing -q`
Expected: >= 90% coverage on sync module
