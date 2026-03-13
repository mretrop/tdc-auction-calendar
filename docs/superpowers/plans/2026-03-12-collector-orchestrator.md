# Collector Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the collector orchestrator that runs all 13 collectors sequentially, deduplicates across them, and upserts results to the database with health tracking.

**Architecture:** Three new files with clean separation — `models/health.py` (data models), `db/upsert.py` (persistence), `collectors/orchestrator.py` (coordination). The orchestrator is pure async with no DB dependency; `run_and_persist` bridges async orchestration and synchronous DB operations.

**Tech Stack:** SQLAlchemy ORM (sync), Pydantic v2, structlog, asyncio, Alembic migrations

**Spec:** `docs/superpowers/specs/2026-03-12-collector-orchestrator-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/tdc_auction_calendar/models/health.py` | Create | `CollectorHealthRow` (ORM), `CollectorHealth` (Pydantic), `CollectorError`, `RunReport`, `UpsertResult` |
| `src/tdc_auction_calendar/models/__init__.py` | Modify | Export new models |
| `src/tdc_auction_calendar/db/upsert.py` | Create | `upsert_auctions`, `save_collector_health`, `get_collector_health` |
| `src/tdc_auction_calendar/collectors/orchestrator.py` | Create | `COLLECTORS` registry, `run_all`, `cross_dedup`, `run_and_persist` |
| `src/tdc_auction_calendar/collectors/__init__.py` | Modify | Export orchestrator functions |
| `alembic/versions/xxx_add_collector_health.py` | Create | Migration for `collector_health` table |
| `tests/test_health_models.py` | Create | Model validation tests |
| `tests/test_upsert.py` | Create | DB upsert + health persistence tests |
| `tests/test_orchestrator.py` | Create | Orchestrator logic tests with mock collectors |

---

## Chunk 1: Data Models

### Task 1: CollectorHealthRow ORM + Pydantic models

**Files:**
- Create: `src/tdc_auction_calendar/models/health.py`
- Test: `tests/test_health_models.py`

- [ ] **Step 1: Write failing tests for health models**

Create `tests/test_health_models.py`:

```python
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
            name="broken", error="timeout", error_type="TimeoutError"
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_health_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tdc_auction_calendar.models.health'`

- [ ] **Step 3: Create the health models file**

Create `src/tdc_auction_calendar/models/health.py`:

```python
"""Health tracking and orchestrator report models."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column

from tdc_auction_calendar.models.jurisdiction import Base


class CollectorHealthRow(Base):
    """Tracks per-collector run health."""

    __tablename__ = "collector_health"

    collector_name: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    last_run: Mapped[datetime.datetime] = mapped_column(sa.DateTime)
    last_success: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime)
    records_collected: Mapped[int] = mapped_column(sa.Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(sa.Text)


class CollectorHealth(BaseModel):
    """Pydantic model for collector health status."""

    collector_name: str
    last_run: datetime.datetime
    last_success: datetime.datetime | None = None
    records_collected: int = 0
    error_message: str | None = None


class CollectorError(BaseModel):
    """A single collector failure in a run."""

    name: str
    error: str
    error_type: str


class RunReport(BaseModel):
    """Result of an orchestrator run."""

    total_records: int
    new_records: int = 0
    updated_records: int = 0
    skipped_records: int = 0
    collectors_succeeded: list[str]
    collectors_failed: list[CollectorError]
    per_collector_counts: dict[str, int] = {}
    duration_seconds: float


class UpsertResult(BaseModel):
    """Counts from a batch upsert operation."""

    new: int
    updated: int
    skipped: int
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_health_models.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Update models/__init__.py exports**

Add to `src/tdc_auction_calendar/models/__init__.py`:

```python
from tdc_auction_calendar.models.health import (
    CollectorError,
    CollectorHealth,
    CollectorHealthRow,
    RunReport,
    UpsertResult,
)
```

And add to `__all__`:
```python
"CollectorError",
"CollectorHealth",
"CollectorHealthRow",
"RunReport",
"UpsertResult",
```

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `uv run pytest --tb=short`
Expected: All tests PASS (existing 321 + 5 new)

- [ ] **Step 7: Generate Alembic migration**

Run: `uv run alembic revision --autogenerate -m "add collector_health table"`
Then: `uv run alembic upgrade head`
Expected: Migration created, applies cleanly

- [ ] **Step 8: Commit**

```bash
git add src/tdc_auction_calendar/models/health.py src/tdc_auction_calendar/models/__init__.py tests/test_health_models.py alembic/versions/*_add_collector_health_table.py
git commit -m "feat: add health and report models for collector orchestrator (issue #15)"
```

---

## Chunk 2: Upsert Layer

### Task 2: Auction upsert (confidence-gated)

**Files:**
- Create: `src/tdc_auction_calendar/db/upsert.py`
- Test: `tests/test_upsert.py`

- [ ] **Step 1: Write failing tests for upsert_auctions**

Create `tests/test_upsert.py`:

```python
"""Tests for auction upsert and health persistence."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from tdc_auction_calendar.db.upsert import (
    get_collector_health,
    save_collector_health,
    upsert_auctions,
)
from tdc_auction_calendar.models import Auction, AuctionRow, UpsertResult
from tdc_auction_calendar.models.health import CollectorHealth, CollectorHealthRow


def _make_auction(**overrides) -> Auction:
    """Build a valid Auction with sensible defaults."""
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


class TestUpsertAuctions:
    def test_insert_new_record(self, db_session):
        """New auction is inserted."""
        auction = _make_auction()
        result = upsert_auctions(db_session, [auction])

        assert result.new == 1
        assert result.updated == 0
        assert result.skipped == 0

        row = db_session.query(AuctionRow).one()
        assert row.state == "FL"
        assert row.county == "Miami-Dade"
        assert row.confidence_score == 0.75

    def test_update_higher_confidence(self, db_session):
        """Higher confidence auction replaces existing."""
        low = _make_auction(confidence_score=0.40, source_type="statutory")
        upsert_auctions(db_session, [low])

        high = _make_auction(
            confidence_score=0.85,
            source_type="state_agency",
            source_url="https://example.com",
        )
        result = upsert_auctions(db_session, [high])

        assert result.new == 0
        assert result.updated == 1
        assert result.skipped == 0

        row = db_session.query(AuctionRow).one()
        assert row.confidence_score == 0.85
        assert row.source_type == "state_agency"
        assert row.source_url == "https://example.com"

    def test_skip_equal_confidence(self, db_session):
        """Equal confidence auction is skipped."""
        first = _make_auction(confidence_score=0.75)
        upsert_auctions(db_session, [first])

        second = _make_auction(confidence_score=0.75, notes="duplicate")
        result = upsert_auctions(db_session, [second])

        assert result.skipped == 1
        assert result.updated == 0

    def test_skip_lower_confidence(self, db_session):
        """Lower confidence auction is skipped."""
        high = _make_auction(confidence_score=0.85)
        upsert_auctions(db_session, [high])

        low = _make_auction(confidence_score=0.40)
        result = upsert_auctions(db_session, [low])

        assert result.skipped == 1

        row = db_session.query(AuctionRow).one()
        assert row.confidence_score == 0.85

    def test_update_replaces_none_values(self, db_session):
        """Higher confidence replaces all fields including None overwrite."""
        original = _make_auction(
            confidence_score=0.40,
            source_url="https://example.com",
            notes="original",
        )
        upsert_auctions(db_session, [original])

        replacement = _make_auction(
            confidence_score=0.85,
            source_url=None,
            notes=None,
        )
        result = upsert_auctions(db_session, [replacement])

        assert result.updated == 1
        row = db_session.query(AuctionRow).one()
        assert row.source_url is None
        assert row.notes is None

    def test_batch_insert_multiple(self, db_session):
        """Multiple new auctions in one call."""
        auctions = [
            _make_auction(county="Miami-Dade"),
            _make_auction(county="Broward"),
            _make_auction(county="Palm Beach"),
        ]
        result = upsert_auctions(db_session, [auctions[0], auctions[1], auctions[2]])

        assert result.new == 3
        assert db_session.query(AuctionRow).count() == 3

    def test_mixed_operations(self, db_session):
        """Mix of inserts, updates, and skips in one call."""
        existing = _make_auction(county="Miami-Dade", confidence_score=0.75)
        upsert_auctions(db_session, [existing])

        batch = [
            _make_auction(county="Miami-Dade", confidence_score=0.85),  # update
            _make_auction(county="Broward", confidence_score=0.75),     # new
        ]
        result = upsert_auctions(db_session, batch)

        assert result.new == 1
        assert result.updated == 1

    def test_empty_list(self, db_session):
        """Empty auction list returns zero counts."""
        result = upsert_auctions(db_session, [])
        assert result == UpsertResult(new=0, updated=0, skipped=0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_upsert.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tdc_auction_calendar.db.upsert'`

- [ ] **Step 3: Implement upsert_auctions**

Create `src/tdc_auction_calendar/db/upsert.py`:

```python
"""Auction upsert and collector health persistence."""

from __future__ import annotations

import datetime

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tdc_auction_calendar.models.auction import Auction, AuctionRow
from tdc_auction_calendar.models.health import (
    CollectorHealth,
    CollectorHealthRow,
    UpsertResult,
)

logger = structlog.get_logger()

# Fields to copy from Auction to AuctionRow on insert/update.
# Excludes: id, created_at, updated_at (managed by DB/ORM).
_UPSERT_FIELDS = [
    "state",
    "county",
    "start_date",
    "end_date",
    "sale_type",
    "status",
    "source_type",
    "source_url",
    "registration_deadline",
    "deposit_deadline",
    "deposit_amount",
    "min_bid",
    "interest_rate",
    "confidence_score",
    "property_count",
    "vendor",
    "notes",
]


_ENUM_FIELDS = frozenset(("sale_type", "status", "source_type"))


def _field_value(auction: Auction, field: str):
    """Get field value, converting enums to their string value."""
    value = getattr(auction, field)
    if field in _ENUM_FIELDS and value is not None:
        return value.value if hasattr(value, "value") else value
    return value


def upsert_auctions(session: Session, auctions: list[Auction]) -> UpsertResult:
    """Upsert auctions by dedup key. Higher confidence wins.

    Does NOT commit — caller is responsible for committing the session.
    """
    new = 0
    updated = 0
    skipped = 0

    for auction in auctions:
        existing = (
            session.query(AuctionRow)
            .filter_by(
                state=auction.state,
                county=auction.county,
                start_date=auction.start_date,
                sale_type=auction.sale_type.value,
            )
            .first()
        )

        if existing is None:
            row = AuctionRow(
                **{field: _field_value(auction, field) for field in _UPSERT_FIELDS}
            )
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                skipped += 1
                logger.warning("upsert_integrity_error", state=auction.state, county=auction.county)
                continue
            new += 1
        elif auction.confidence_score > existing.confidence_score:
            for field in _UPSERT_FIELDS:
                setattr(existing, field, _field_value(auction, field))
            updated += 1
        else:
            skipped += 1

    session.flush()
    logger.info("upsert_complete", new=new, updated=updated, skipped=skipped)
    return UpsertResult(new=new, updated=updated, skipped=skipped)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_upsert.py::TestUpsertAuctions -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/db/upsert.py tests/test_upsert.py
git commit -m "feat: add auction upsert with confidence gating (issue #15)"
```

### Task 3: Health persistence

**Files:**
- Modify: `src/tdc_auction_calendar/db/upsert.py`
- Test: `tests/test_upsert.py`

- [ ] **Step 1: Write failing tests for health persistence**

Add to `tests/test_upsert.py`:

```python
class TestSaveCollectorHealth:
    def test_save_success(self, db_session):
        """Successful run records health."""
        save_collector_health(
            db_session,
            name="florida_public_notice",
            success=True,
            records=42,
            error=None,
        )

        row = db_session.query(CollectorHealthRow).one()
        assert row.collector_name == "florida_public_notice"
        assert row.records_collected == 42
        assert row.last_success is not None
        assert row.error_message is None

    def test_save_failure(self, db_session):
        """Failed run records error, no last_success."""
        save_collector_health(
            db_session,
            name="broken_collector",
            success=False,
            records=0,
            error="Connection refused",
        )

        row = db_session.query(CollectorHealthRow).one()
        assert row.error_message == "Connection refused"
        assert row.last_success is None

    def test_success_after_failure_clears_error(self, db_session):
        """Success after failure clears error_message."""
        save_collector_health(
            db_session, name="flaky", success=False, records=0, error="timeout"
        )
        save_collector_health(
            db_session, name="flaky", success=True, records=10, error=None
        )

        row = db_session.query(CollectorHealthRow).one()
        assert row.error_message is None
        assert row.records_collected == 10
        assert row.last_success is not None

    def test_failure_preserves_last_success(self, db_session):
        """Failure after success preserves last_success and records_collected."""
        save_collector_health(
            db_session, name="flaky", success=True, records=10, error=None
        )
        first_success = db_session.query(CollectorHealthRow).one().last_success

        save_collector_health(
            db_session, name="flaky", success=False, records=0, error="boom"
        )

        row = db_session.query(CollectorHealthRow).one()
        assert row.last_success == first_success
        assert row.records_collected == 10
        assert row.error_message == "boom"


class TestGetCollectorHealth:
    def test_get_empty(self, db_session):
        """Returns empty list when no health rows exist."""
        result = get_collector_health(db_session)
        assert result == []

    def test_get_returns_pydantic_models(self, db_session):
        """Returns CollectorHealth Pydantic models."""
        save_collector_health(
            db_session, name="test", success=True, records=5, error=None
        )
        result = get_collector_health(db_session)

        assert len(result) == 1
        assert isinstance(result[0], CollectorHealth)
        assert result[0].collector_name == "test"
        assert result[0].records_collected == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_upsert.py::TestSaveCollectorHealth -v`
Expected: FAIL — `ImportError: cannot import name 'save_collector_health'`

- [ ] **Step 3: Implement save_collector_health and get_collector_health**

Add to `src/tdc_auction_calendar/db/upsert.py`:

```python
def save_collector_health(
    session: Session,
    name: str,
    success: bool,
    records: int,
    error: str | None,
) -> None:
    """Upsert collector health after a run.

    Does NOT commit — caller is responsible for committing the session.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    row = session.get(CollectorHealthRow, name)

    if row is None:
        row = CollectorHealthRow(
            collector_name=name,
            last_run=now,
            last_success=now if success else None,
            records_collected=records if success else 0,
            error_message=None if success else error,
        )
        session.add(row)
    else:
        row.last_run = now
        if success:
            row.last_success = now
            row.records_collected = records
            row.error_message = None
        else:
            row.error_message = error

    session.flush()


def get_collector_health(session: Session) -> list[CollectorHealth]:
    """Return all collector health records as Pydantic models."""
    rows = session.query(CollectorHealthRow).all()
    return [
        CollectorHealth(
            collector_name=row.collector_name,
            last_run=row.last_run,
            last_success=row.last_success,
            records_collected=row.records_collected,
            error_message=row.error_message,
        )
        for row in rows
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_upsert.py -v`
Expected: All 14 tests PASS (8 upsert + 6 health)

- [ ] **Step 5: Run full suite for regressions**

Run: `uv run pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/db/upsert.py tests/test_upsert.py
git commit -m "feat: add health persistence and query for collector orchestrator (issue #15)"
```

---

## Chunk 3: Orchestrator

### Task 4: Cross-collector dedup utility

**Files:**
- Create: `src/tdc_auction_calendar/collectors/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests for cross_dedup**

Create `tests/test_orchestrator.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator.py::TestCrossDedup -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create orchestrator with registry and cross_dedup**

Create `src/tdc_auction_calendar/collectors/orchestrator.py`:

```python
"""Collector orchestrator — runs collectors, deduplicates, reports."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.county_websites import CountyWebsiteCollector
from tdc_auction_calendar.collectors.public_notices import (
    FloridaCollector,
    MinnesotaCollector,
    NewJerseyCollector,
    NorthCarolinaCollector,
    PennsylvaniaCollector,
    SouthCarolinaCollector,
    UtahCollector,
)
from tdc_auction_calendar.collectors.state_agencies import (
    ArkansasCollector,
    CaliforniaCollector,
    ColoradoCollector,
    IowaCollector,
)
from tdc_auction_calendar.collectors.statutory import StatutoryCollector
from tdc_auction_calendar.models.auction import Auction, DeduplicationKey
from tdc_auction_calendar.models.health import CollectorError, RunReport

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = structlog.get_logger()

COLLECTORS: dict[str, type[BaseCollector]] = {
    "florida_public_notice": FloridaCollector,
    "minnesota_public_notice": MinnesotaCollector,
    "new_jersey_public_notice": NewJerseyCollector,
    "north_carolina_public_notice": NorthCarolinaCollector,
    "pennsylvania_public_notice": PennsylvaniaCollector,
    "south_carolina_public_notice": SouthCarolinaCollector,
    "utah_public_notice": UtahCollector,
    "arkansas_state_agency": ArkansasCollector,
    "california_state_agency": CaliforniaCollector,
    "colorado_state_agency": ColoradoCollector,
    "iowa_state_agency": IowaCollector,
    "county_website": CountyWebsiteCollector,
    "statutory": StatutoryCollector,
}


def cross_dedup(auctions: list[Auction]) -> list[Auction]:
    """Deduplicate across collectors. Keeps highest confidence_score per dedup key."""
    best: dict[DeduplicationKey, Auction] = {}
    for auction in auctions:
        key = auction.dedup_key
        existing = best.get(key)
        if existing is None or auction.confidence_score > existing.confidence_score:
            best[key] = auction

    before = len(auctions)
    after = len(best)
    logger.info("cross_dedup_complete", before=before, after=after)

    return list(best.values())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator.py::TestCrossDedup -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add collector registry and cross-dedup (issue #15)"
```

### Task 5: run_all function

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests for run_all**

Add to `tests/test_orchestrator.py`:

```python
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
        assert report.collectors_failed[0].name == "fail"
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator.py::TestRunAll -v`
Expected: FAIL — `ImportError: cannot import name 'run_all'`

- [ ] **Step 3: Implement run_all**

Add to `src/tdc_auction_calendar/collectors/orchestrator.py`:

```python
async def run_all(
    collectors: list[str] | None = None,
) -> tuple[list[Auction], RunReport]:
    """Run collectors sequentially, deduplicate, and return results with report."""
    # 1. Resolve collector list
    if collectors is not None:
        unknown = set(collectors) - set(COLLECTORS)
        if unknown:
            raise ValueError(f"Unknown collector names: {sorted(unknown)}")
        to_run = {name: COLLECTORS[name] for name in collectors}
    else:
        to_run = COLLECTORS

    # 2. Execute sequentially
    start = time.monotonic()
    all_auctions: list[Auction] = []
    succeeded: list[str] = []
    failed: list[CollectorError] = []
    per_collector_counts: dict[str, int] = {}

    for name, cls in to_run.items():
        logger.info("collector_start", collector=name)
        try:
            collector = cls()
            results = await collector.collect()
            all_auctions.extend(results)
            succeeded.append(name)
            per_collector_counts[name] = len(results)
            logger.info("collector_complete", collector=name, records=len(results))
        except Exception as exc:
            failed.append(
                CollectorError(
                    name=name,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
            )
            logger.warning("collector_failed", collector=name, error=str(exc))

    # 3. Cross-collector dedup
    deduped = cross_dedup(all_auctions)

    # 4. Build report
    elapsed = time.monotonic() - start
    report = RunReport(
        total_records=len(deduped),
        collectors_succeeded=succeeded,
        collectors_failed=failed,
        per_collector_counts=per_collector_counts,
        duration_seconds=round(elapsed, 3),
    )

    return deduped, report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: All 10 tests PASS (4 dedup + 6 run_all)

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add run_all orchestrator function (issue #15)"
```

### Task 6: run_and_persist function

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests for run_and_persist**

Add to `tests/test_orchestrator.py`:

```python
from tdc_auction_calendar.collectors.orchestrator import run_and_persist
from tdc_auction_calendar.models import AuctionRow
from tdc_auction_calendar.models.health import CollectorHealthRow


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator.py::TestRunAndPersist -v`
Expected: FAIL — `ImportError: cannot import name 'run_and_persist'`

- [ ] **Step 3: Implement run_and_persist**

Add to `src/tdc_auction_calendar/collectors/orchestrator.py`:

```python
from tdc_auction_calendar.db.upsert import save_collector_health, upsert_auctions


async def run_and_persist(
    session: Session,
    collectors: list[str] | None = None,
) -> RunReport:
    """Run all collectors and persist results to the database."""
    auctions, report = await run_all(collectors)

    # Upsert auctions
    upsert_result = upsert_auctions(session, auctions)
    report.new_records = upsert_result.new
    report.updated_records = upsert_result.updated
    report.skipped_records = upsert_result.skipped

    # Save health for each collector (using per-collector counts)
    for name in report.collectors_succeeded:
        save_collector_health(
            session, name=name, success=True,
            records=report.per_collector_counts.get(name, 0), error=None,
        )
    for err in report.collectors_failed:
        save_collector_health(session, name=err.name, success=False, records=0, error=err.error)

    # Single commit for all DB writes
    session.commit()

    return report
```

Note: The `RunReport` model needs to allow mutation for `run_and_persist` to set DB counts. Either remove `frozen` from the model config or use a different approach. Since `RunReport` is not frozen by default (it's a plain `BaseModel`), direct attribute assignment works.

Also update the import at the top of the file — move `Session` out of `TYPE_CHECKING`:

```python
from sqlalchemy.orm import Session
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Update collectors/__init__.py exports**

Add to `src/tdc_auction_calendar/collectors/__init__.py`:

```python
from tdc_auction_calendar.collectors.orchestrator import (
    COLLECTORS,
    cross_dedup,
    run_all,
    run_and_persist,
)
```

And add to `__all__`:
```python
"COLLECTORS",
"cross_dedup",
"run_all",
"run_and_persist",
```

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/tdc_auction_calendar/collectors/orchestrator.py src/tdc_auction_calendar/collectors/__init__.py tests/test_orchestrator.py
git commit -m "feat: add run_and_persist with DB upsert and health tracking (issue #15)"
```

---

## Chunk 4: Final Verification

### Task 7: Full integration test and cleanup

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: All tests PASS (321 existing + ~35 new)

- [ ] **Step 2: Verify registry matches collector names**

Add a test to `tests/test_orchestrator.py`:

```python
class TestRegistry:
    def test_registry_has_13_collectors(self):
        """Registry contains all 13 collectors."""
        assert len(COLLECTORS) == 13

    def test_registry_keys_match_collector_names(self):
        """Registry keys match each collector's .name property."""
        for key, cls in COLLECTORS.items():
            instance = cls()
            assert key == instance.name, f"Registry key {key!r} != {cls.__name__}.name {instance.name!r}"
```

- [ ] **Step 3: Run registry test**

Run: `uv run pytest tests/test_orchestrator.py::TestRegistry -v`
Expected: PASS

- [ ] **Step 4: Run full test suite one final time**

Run: `uv run pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_orchestrator.py
git commit -m "test: add registry validation for collector orchestrator (issue #15)"
```
