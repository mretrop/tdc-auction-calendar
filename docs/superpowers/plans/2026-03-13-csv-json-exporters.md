# CSV + JSON Exporters Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CSV and JSON export formats with a shared query/filter layer extracted from the iCal exporter.

**Architecture:** Extract `query_auctions()` from `exporters/ical.py` into `exporters/filters.py`, add `upcoming_only` parameter. Build `csv_export.py` and `json_export.py` following the same `auctions_to_<format>(list[Auction]) -> str` pattern. Wire both into the CLI's `export_app` replacing stubs.

**Tech Stack:** Python stdlib `csv`/`json`, Pydantic `model_dump`, Typer CLI, SQLAlchemy queries

---

## Chunk 1: Shared Query Layer

### Task 1: Extract `query_auctions` into `filters.py` with tests

**Files:**
- Create: `src/tdc_auction_calendar/exporters/filters.py`
- Modify: `src/tdc_auction_calendar/exporters/ical.py:1-14,92-123`
- Modify: `tests/test_ical_export.py:10`
- Create: `tests/test_export_filters.py`

- [ ] **Step 1: Write the failing test for `upcoming_only` filter**

Create `tests/test_export_filters.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export_filters.py -v`
Expected: FAIL — `ImportError: cannot import name 'query_auctions' from 'tdc_auction_calendar.exporters.filters'`

- [ ] **Step 3: Create `filters.py` by extracting from `ical.py`**

Create `src/tdc_auction_calendar/exporters/filters.py`:

```python
"""Shared query/filter utilities for all exporters."""

from __future__ import annotations

import datetime

import structlog
from sqlalchemy.orm import Session

from tdc_auction_calendar.models.auction import Auction, AuctionRow
from tdc_auction_calendar.models.enums import AuctionStatus, SaleType

logger = structlog.get_logger()


def query_auctions(
    session: Session,
    states: list[str] | None = None,
    sale_type: SaleType | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
    upcoming_only: bool = False,
) -> list[Auction]:
    """Query auctions from the DB with optional filters, return Pydantic models."""
    logger.debug(
        "querying auctions",
        states=states,
        sale_type=str(sale_type) if sale_type else None,
        from_date=str(from_date) if from_date else None,
        to_date=str(to_date) if to_date else None,
        upcoming_only=upcoming_only,
    )
    query = session.query(AuctionRow)

    if states:
        query = query.filter(AuctionRow.state.in_([s.upper() for s in states]))
    if sale_type:
        query = query.filter(AuctionRow.sale_type == str(sale_type))
    if from_date:
        query = query.filter(AuctionRow.start_date >= from_date)
    else:
        query = query.filter(AuctionRow.start_date >= datetime.date.today())
    if to_date:
        query = query.filter(AuctionRow.start_date <= to_date)
    if upcoming_only:
        query = query.filter(AuctionRow.status == str(AuctionStatus.UPCOMING))

    rows = query.order_by(AuctionRow.start_date).all()
    auctions = [Auction.model_validate(r, from_attributes=True) for r in rows]
    logger.info("queried auctions", count=len(auctions))
    return auctions
```

- [ ] **Step 4: Run new filter tests to verify they pass**

Run: `uv run pytest tests/test_export_filters.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Update `ical.py` to import from `filters.py`**

In `src/tdc_auction_calendar/exporters/ical.py`:
- Remove the `query_auctions` function (lines 92-123)
- Remove unused imports: `Session` from sqlalchemy, `AuctionRow`, `SaleType`
- Add re-export at the top for backwards compatibility:

```python
from tdc_auction_calendar.exporters.filters import query_auctions  # noqa: F401
```

The final `ical.py` imports section becomes:

```python
from __future__ import annotations

import datetime

import structlog
from icalendar import Alarm, Calendar, Event

from tdc_auction_calendar.exporters.filters import query_auctions  # noqa: F401
from tdc_auction_calendar.models.auction import Auction

logger = structlog.get_logger()
```

Everything else in `ical.py` (lines 17-89) stays unchanged.

- [ ] **Step 6: Run all existing iCal tests to verify no regression**

Run: `uv run pytest tests/test_ical_export.py -v`
Expected: All 20 tests PASS — the re-export in `ical.py` means `from tdc_auction_calendar.exporters.ical import query_auctions` still works.

- [ ] **Step 7: Commit**

```bash
git add src/tdc_auction_calendar/exporters/filters.py tests/test_export_filters.py src/tdc_auction_calendar/exporters/ical.py
git commit -m "refactor: extract query_auctions into shared filters module (issue #19)"
```

---

## Chunk 2: CSV Exporter

### Task 2: CSV exporter with round-trip test

**Files:**
- Create: `src/tdc_auction_calendar/exporters/csv_export.py`
- Create: `tests/test_csv_export.py`

- [ ] **Step 1: Write the failing round-trip test**

Create `tests/test_csv_export.py`:

```python
"""Tests for CSV exporter."""

from __future__ import annotations

import csv
import datetime
import io
from decimal import Decimal

from tdc_auction_calendar.exporters.csv_export import CSV_COLUMNS, auctions_to_csv
from tdc_auction_calendar.models.auction import Auction


def _make_auction(**overrides) -> Auction:
    """Build an Auction with sensible defaults."""
    defaults = {
        "state": "FL",
        "county": "Miami-Dade",
        "start_date": datetime.date(2027, 4, 15),
        "end_date": datetime.date(2027, 4, 17),
        "sale_type": "deed",
        "status": "upcoming",
        "source_type": "statutory",
        "confidence_score": 1.0,
    }
    defaults.update(overrides)
    return Auction(**defaults)


class TestAuctionsToCsv:
    def test_empty_list_returns_header_only(self):
        result = auctions_to_csv([])
        reader = csv.DictReader(io.StringIO(result))
        assert reader.fieldnames == list(CSV_COLUMNS)
        assert list(reader) == []

    def test_round_trip_through_dictreader(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_amount=Decimal("5000.00"),
            interest_rate=Decimal("18.00"),
            property_count=150,
            vendor="RealAuction",
            source_url="https://example.com/auction",
        )
        result = auctions_to_csv([auction])
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 1
        row = rows[0]
        assert row["state"] == "FL"
        assert row["county"] == "Miami-Dade"
        assert row["sale_type"] == "deed"
        assert row["start_date"] == "2027-04-15"
        assert row["end_date"] == "2027-04-17"
        assert row["registration_deadline"] == "2027-04-01"
        assert row["deposit_amount"] == "5000.00"
        assert row["interest_rate"] == "18.00"
        assert row["property_count"] == "150"
        assert row["vendor"] == "RealAuction"
        assert row["confidence_score"] == "1.0"
        assert row["source_url"] == "https://example.com/auction"

    def test_null_fields_are_empty_strings(self):
        auction = _make_auction(
            end_date=None,
            registration_deadline=None,
            deposit_amount=None,
            interest_rate=None,
            property_count=None,
            vendor=None,
            source_url=None,
        )
        result = auctions_to_csv([auction])
        reader = csv.DictReader(io.StringIO(result))
        row = next(reader)
        assert row["end_date"] == ""
        assert row["deposit_amount"] == ""
        assert row["vendor"] == ""

    def test_multiple_auctions(self):
        a1 = _make_auction(state="FL")
        a2 = _make_auction(state="TX", county="Harris")
        result = auctions_to_csv([a1, a2])
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["state"] == "FL"
        assert rows[1]["state"] == "TX"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_csv_export.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement CSV exporter**

Create `src/tdc_auction_calendar/exporters/csv_export.py`:

```python
"""CSV exporter — converts Auction models to CSV string."""

from __future__ import annotations

import csv
import io

from tdc_auction_calendar.models.auction import Auction

CSV_COLUMNS = (
    "state",
    "county",
    "sale_type",
    "start_date",
    "end_date",
    "registration_deadline",
    "deposit_amount",
    "interest_rate",
    "property_count",
    "vendor",
    "confidence_score",
    "source_url",
)


def auctions_to_csv(auctions: list[Auction]) -> str:
    """Convert a list of Auction models to a CSV string."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for auction in auctions:
        row = auction.model_dump(mode="json")
        # model_dump converts dates to ISO strings, Decimals to floats/strings
        # Filter to only our columns and convert None to empty string
        filtered = {col: row.get(col) if row.get(col) is not None else "" for col in CSV_COLUMNS}
        writer.writerow(filtered)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_csv_export.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/exporters/csv_export.py tests/test_csv_export.py
git commit -m "feat: CSV exporter (issue #19)"
```

---

## Chunk 3: JSON Exporter

### Task 3: JSON exporter with Pydantic validation test

**Files:**
- Create: `src/tdc_auction_calendar/exporters/json_export.py`
- Create: `tests/test_json_export.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_json_export.py`:

```python
"""Tests for JSON exporter."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

from tdc_auction_calendar.exporters.json_export import auctions_to_json
from tdc_auction_calendar.models.auction import Auction


def _make_auction(**overrides) -> Auction:
    """Build an Auction with sensible defaults."""
    defaults = {
        "state": "FL",
        "county": "Miami-Dade",
        "start_date": datetime.date(2027, 4, 15),
        "end_date": datetime.date(2027, 4, 17),
        "sale_type": "deed",
        "status": "upcoming",
        "source_type": "statutory",
        "confidence_score": 1.0,
    }
    defaults.update(overrides)
    return Auction(**defaults)


class TestAuctionsToJson:
    def test_empty_list_returns_empty_array(self):
        result = auctions_to_json([])
        assert json.loads(result) == []

    def test_round_trip_validates_against_pydantic(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_amount=Decimal("5000.00"),
            source_url="https://example.com/auction",
        )
        result = auctions_to_json([auction])
        parsed = json.loads(result)
        assert len(parsed) == 1
        # Validate each object against Pydantic model
        restored = Auction(**parsed[0])
        assert restored.state == "FL"
        assert restored.start_date == datetime.date(2027, 4, 15)
        assert restored.deposit_amount == Decimal("5000.00")

    def test_compact_mode_no_whitespace(self):
        auction = _make_auction()
        result = auctions_to_json([auction], compact=True)
        assert "\n" not in result
        # Still valid JSON
        json.loads(result)

    def test_pretty_mode_has_indentation(self):
        auction = _make_auction()
        result = auctions_to_json([auction], compact=False)
        assert "\n" in result
        lines = result.split("\n")
        # Should have indented lines
        assert any(line.startswith("  ") for line in lines)

    def test_all_auction_fields_present(self):
        auction = _make_auction()
        result = auctions_to_json([auction])
        parsed = json.loads(result)[0]
        expected_fields = set(Auction.model_fields.keys())
        assert set(parsed.keys()) == expected_fields

    def test_multiple_auctions(self):
        a1 = _make_auction(state="FL")
        a2 = _make_auction(state="TX", county="Harris")
        result = auctions_to_json([a1, a2])
        parsed = json.loads(result)
        assert len(parsed) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_json_export.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement JSON exporter**

Create `src/tdc_auction_calendar/exporters/json_export.py`:

```python
"""JSON exporter — converts Auction models to JSON string."""

from __future__ import annotations

import json

from tdc_auction_calendar.models.auction import Auction


def auctions_to_json(auctions: list[Auction], compact: bool = False) -> str:
    """Convert a list of Auction models to a JSON string."""
    data = [auction.model_dump(mode="json") for auction in auctions]
    if compact:
        return json.dumps(data, separators=(",", ":"))
    return json.dumps(data, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_json_export.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/exporters/json_export.py tests/test_json_export.py
git commit -m "feat: JSON exporter (issue #19)"
```

---

## Chunk 4: CLI Wiring

### Task 4: Wire CSV and JSON commands into CLI

**Files:**
- Modify: `src/tdc_auction_calendar/cli.py:119-131`

- [ ] **Step 1: Replace CSV stub in `cli.py`**

Replace the `export_csv` function (lines 119-123) with:

```python
@export_app.command("csv")
def export_csv(
    state: list[str] | None = typer.Option(None, "--state", help="Filter by state code (repeatable)"),
    sale_type: SaleType | None = typer.Option(None, "--sale-type", help="Filter by sale type"),
    from_date: str | None = typer.Option(None, "--from-date", help="Start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, "--to-date", help="End date (YYYY-MM-DD)"),
    upcoming_only: bool = typer.Option(False, "--upcoming-only", help="Only include upcoming auctions"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
    """Export auctions to CSV format."""
    import sys

    from tdc_auction_calendar.exporters.csv_export import auctions_to_csv
    from tdc_auction_calendar.exporters.filters import query_auctions

    if not _check_db_exists():
        console.print("[red]Database not found.[/red] Run `tdc-auction-calendar collect` first.")
        raise typer.Exit(1)

    from_date_parsed: datetime.date | None = None
    to_date_parsed: datetime.date | None = None
    try:
        if from_date:
            from_date_parsed = datetime.date.fromisoformat(from_date)
        if to_date:
            to_date_parsed = datetime.date.fromisoformat(to_date)
    except ValueError:
        console.print(f"[red]Invalid date format.[/red] Use YYYY-MM-DD (e.g., {datetime.date.today().isoformat()}).")
        raise typer.Exit(1)

    session = get_session()
    try:
        auctions = query_auctions(
            session,
            states=state,
            sale_type=sale_type,
            from_date=from_date_parsed,
            to_date=to_date_parsed,
            upcoming_only=upcoming_only,
        )
    except Exception as exc:
        console.print(f"[red]Database query failed:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        session.close()

    csv_str = auctions_to_csv(auctions)

    try:
        if output:
            with open(output, "w", newline="") as f:
                f.write(csv_str)
        else:
            sys.stdout.write(csv_str)
    except (OSError, BrokenPipeError) as exc:
        console.print(f"[red]Failed to write output:[/red] {exc}")
        raise typer.Exit(1)

    typer.echo(f"Exported {len(auctions)} auction(s).", err=True)
```

- [ ] **Step 2: Replace JSON stub in `cli.py`**

Replace the `export_json` function (lines 126-130) with:

```python
@export_app.command("json")
def export_json(
    state: list[str] | None = typer.Option(None, "--state", help="Filter by state code (repeatable)"),
    sale_type: SaleType | None = typer.Option(None, "--sale-type", help="Filter by sale type"),
    from_date: str | None = typer.Option(None, "--from-date", help="Start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, "--to-date", help="End date (YYYY-MM-DD)"),
    upcoming_only: bool = typer.Option(False, "--upcoming-only", help="Only include upcoming auctions"),
    compact: bool = typer.Option(False, "--compact", help="Single-line output (no indentation)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
    """Export auctions to JSON format."""
    import sys

    from tdc_auction_calendar.exporters.json_export import auctions_to_json
    from tdc_auction_calendar.exporters.filters import query_auctions

    if not _check_db_exists():
        console.print("[red]Database not found.[/red] Run `tdc-auction-calendar collect` first.")
        raise typer.Exit(1)

    from_date_parsed: datetime.date | None = None
    to_date_parsed: datetime.date | None = None
    try:
        if from_date:
            from_date_parsed = datetime.date.fromisoformat(from_date)
        if to_date:
            to_date_parsed = datetime.date.fromisoformat(to_date)
    except ValueError:
        console.print(f"[red]Invalid date format.[/red] Use YYYY-MM-DD (e.g., {datetime.date.today().isoformat()}).")
        raise typer.Exit(1)

    session = get_session()
    try:
        auctions = query_auctions(
            session,
            states=state,
            sale_type=sale_type,
            from_date=from_date_parsed,
            to_date=to_date_parsed,
            upcoming_only=upcoming_only,
        )
    except Exception as exc:
        console.print(f"[red]Database query failed:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        session.close()

    json_str = auctions_to_json(auctions, compact=compact)

    try:
        if output:
            with open(output, "w") as f:
                f.write(json_str)
        else:
            sys.stdout.write(json_str)
            sys.stdout.write("\n")
    except (OSError, BrokenPipeError) as exc:
        console.print(f"[red]Failed to write output:[/red] {exc}")
        raise typer.Exit(1)

    typer.echo(f"Exported {len(auctions)} auction(s).", err=True)
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/tdc_auction_calendar/cli.py
git commit -m "feat: wire CSV + JSON export commands into CLI (issue #19)"
```
