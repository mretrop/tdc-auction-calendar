# iCalendar Exporter Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export auction records as RFC 5545 .ics files with filtering, VALARMs, and CLI integration.

**Architecture:** Pure function `auctions_to_ical()` converts Pydantic `Auction` models to iCalendar bytes using the `icalendar` library. A `query_auctions()` helper handles DB filtering. The CLI command wires them together with stdout/file output.

**Tech Stack:** icalendar (v7.0.3, already a dependency), SQLAlchemy, Pydantic, Typer

**Spec:** `docs/superpowers/specs/2026-03-13-ical-exporter-design.md`

---

## Chunk 1: Core Export Function

### Task 1: `auctions_to_ical` — basic VEVENT generation

**Files:**
- Create: `src/tdc_auction_calendar/exporters/ical.py`
- Create: `tests/test_ical_export.py`

- [ ] **Step 1: Write failing test for empty calendar**

```python
# tests/test_ical_export.py
"""Tests for iCalendar exporter."""

from __future__ import annotations

import datetime
from decimal import Decimal

from icalendar import Calendar

from tdc_auction_calendar.exporters.ical import auctions_to_ical
from tdc_auction_calendar.models.auction import Auction


def _make_auction(**overrides) -> Auction:
    """Build an Auction with sensible defaults; override any field."""
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


class TestAuctionsToIcalBasic:
    def test_empty_list_returns_valid_calendar(self):
        result = auctions_to_ical([])
        cal = Calendar.from_ical(result)
        assert cal["PRODID"] == "-//TDC Auction Calendar//EN"
        assert cal["VERSION"] == "2.0"
        # No VEVENTs
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert events == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ical_export.py::TestAuctionsToIcalBasic::test_empty_list_returns_valid_calendar -v`
Expected: FAIL — `ModuleNotFoundError` (module doesn't exist yet)

- [ ] **Step 3: Write minimal implementation for empty calendar**

```python
# src/tdc_auction_calendar/exporters/ical.py
"""iCalendar exporter — converts Auction models to RFC 5545 .ics bytes."""

from __future__ import annotations

from icalendar import Calendar

from tdc_auction_calendar.models.auction import Auction


def auctions_to_ical(auctions: list[Auction]) -> bytes:
    """Convert a list of Auction models to iCalendar bytes."""
    cal = Calendar()
    cal.add("prodid", "-//TDC Auction Calendar//EN")
    cal.add("version", "2.0")
    return cal.to_ical()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ical_export.py::TestAuctionsToIcalBasic::test_empty_list_returns_valid_calendar -v`
Expected: PASS

- [ ] **Step 5: Write failing test for single auction VEVENT**

Add to `TestAuctionsToIcalBasic` in `tests/test_ical_export.py`:

```python
    def test_single_auction_produces_vevent(self):
        auction = _make_auction()
        result = auctions_to_ical([auction])
        cal = Calendar.from_ical(result)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1

    def test_summary_format(self):
        auction = _make_auction(county="Miami-Dade", state="FL", sale_type="deed")
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert str(event["SUMMARY"]) == "Miami-Dade FL Tax Deed Sale"

    def test_dtstart_dtend_with_end_date(self):
        auction = _make_auction(
            start_date=datetime.date(2027, 4, 15),
            end_date=datetime.date(2027, 4, 17),
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert event["DTSTART"].dt == datetime.date(2027, 4, 15)
        assert event["DTEND"].dt == datetime.date(2027, 4, 17)

    def test_dtend_defaults_to_start_plus_one_when_no_end_date(self):
        auction = _make_auction(
            start_date=datetime.date(2027, 4, 15),
            end_date=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert event["DTEND"].dt == datetime.date(2027, 4, 16)

    def test_uid_is_deterministic(self):
        auction = _make_auction(
            state="FL", county="Miami-Dade",
            start_date=datetime.date(2027, 4, 15),
            sale_type="deed",
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert str(event["UID"]) == "FL-Miami-Dade-2027-04-15-deed@tdc-auction-calendar"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_ical_export.py::TestAuctionsToIcalBasic -v`
Expected: FAIL — no VEVENTs generated

- [ ] **Step 7: Implement VEVENT generation**

Update `auctions_to_ical` in `src/tdc_auction_calendar/exporters/ical.py`:

```python
"""iCalendar exporter — converts Auction models to RFC 5545 .ics bytes."""

from __future__ import annotations

import datetime

from icalendar import Calendar, Event

from tdc_auction_calendar.models.auction import Auction


def _build_event(auction: Auction) -> Event:
    """Build a VEVENT from an Auction model."""
    event = Event()
    event.add("summary", f"{auction.county} {auction.state} Tax {auction.sale_type.title()} Sale")
    event.add("dtstart", auction.start_date)
    event.add("dtend", auction.end_date or auction.start_date + datetime.timedelta(days=1))
    event.add("uid", f"{auction.state}-{auction.county}-{auction.start_date}-{auction.sale_type}@tdc-auction-calendar")
    return event


def auctions_to_ical(auctions: list[Auction]) -> bytes:
    """Convert a list of Auction models to iCalendar bytes."""
    cal = Calendar()
    cal.add("prodid", "-//TDC Auction Calendar//EN")
    cal.add("version", "2.0")
    for auction in auctions:
        cal.add_component(_build_event(auction))
    return cal.to_ical()
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_ical_export.py::TestAuctionsToIcalBasic -v`
Expected: PASS (all 5 tests)

- [ ] **Step 9: Commit**

```bash
git add src/tdc_auction_calendar/exporters/ical.py tests/test_ical_export.py
git commit -m "feat: basic iCal VEVENT generation (issue #18)"
```

### Task 2: DESCRIPTION and URL fields

**Files:**
- Modify: `src/tdc_auction_calendar/exporters/ical.py`
- Modify: `tests/test_ical_export.py`

- [ ] **Step 1: Write failing tests for DESCRIPTION and URL**

Add to `tests/test_ical_export.py`:

```python
class TestDescriptionAndUrl:
    def test_description_with_all_fields(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_amount=Decimal("5000.00"),
            deposit_deadline=datetime.date(2027, 4, 10),
            property_count=150,
            source_url="https://example.com/auction",
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        desc = str(event["DESCRIPTION"])
        assert "Registration deadline: 2027-04-01" in desc
        assert "Deposit amount: $5,000.00" in desc
        assert "Deposit deadline: 2027-04-10" in desc
        assert "Properties: 150" in desc
        assert "Source: https://example.com/auction" in desc

    def test_description_omits_null_fields(self):
        auction = _make_auction(
            registration_deadline=None,
            deposit_amount=None,
            deposit_deadline=None,
            property_count=None,
            source_url=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        # DESCRIPTION should either be absent or empty
        desc = str(event.get("DESCRIPTION", ""))
        assert "Registration" not in desc
        assert "Deposit" not in desc
        assert "Properties" not in desc
        assert "Source" not in desc

    def test_url_present_when_source_url_set(self):
        auction = _make_auction(source_url="https://example.com/auction")
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert str(event["URL"]) == "https://example.com/auction"

    def test_url_absent_when_source_url_null(self):
        auction = _make_auction(source_url=None)
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert "URL" not in event
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ical_export.py::TestDescriptionAndUrl -v`
Expected: FAIL

- [ ] **Step 3: Implement DESCRIPTION and URL**

Replace the full contents of `src/tdc_auction_calendar/exporters/ical.py` with:

```python
"""iCalendar exporter — converts Auction models to RFC 5545 .ics bytes."""

from __future__ import annotations

import datetime

from icalendar import Calendar, Event

from tdc_auction_calendar.models.auction import Auction


def _build_description(auction: Auction) -> str:
    """Build human-readable DESCRIPTION from non-null fields."""
    lines: list[str] = []
    if auction.registration_deadline is not None:
        lines.append(f"Registration deadline: {auction.registration_deadline}")
    if auction.deposit_amount is not None:
        lines.append(f"Deposit amount: ${auction.deposit_amount:,.2f}")
    if auction.deposit_deadline is not None:
        lines.append(f"Deposit deadline: {auction.deposit_deadline}")
    if auction.property_count is not None:
        lines.append(f"Properties: {auction.property_count}")
    if auction.source_url is not None:
        lines.append(f"Source: {auction.source_url}")
    return "\n".join(lines)


def _build_event(auction: Auction) -> Event:
    """Build a VEVENT from an Auction model."""
    event = Event()
    event.add("summary", f"{auction.county} {auction.state} Tax {auction.sale_type.title()} Sale")
    event.add("dtstart", auction.start_date)
    event.add("dtend", auction.end_date or auction.start_date + datetime.timedelta(days=1))
    event.add("uid", f"{auction.state}-{auction.county}-{auction.start_date}-{auction.sale_type}@tdc-auction-calendar")
    description = _build_description(auction)
    if description:
        event.add("description", description)
    if auction.source_url:
        event.add("url", auction.source_url)
    return event


def auctions_to_ical(auctions: list[Auction]) -> bytes:
    """Convert a list of Auction models to iCalendar bytes."""
    cal = Calendar()
    cal.add("prodid", "-//TDC Auction Calendar//EN")
    cal.add("version", "2.0")
    for auction in auctions:
        cal.add_component(_build_event(auction))
    return cal.to_ical()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ical_export.py::TestDescriptionAndUrl -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/exporters/ical.py tests/test_ical_export.py
git commit -m "feat: iCal DESCRIPTION and URL fields (issue #18)"
```

### Task 3: VALARM triggers

**Files:**
- Modify: `src/tdc_auction_calendar/exporters/ical.py`
- Modify: `tests/test_ical_export.py`

- [ ] **Step 1: Write failing tests for VALARMs**

Add to `tests/test_ical_export.py`:

```python
class TestValarms:
    def test_registration_deadline_produces_two_alarms(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_deadline=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        assert len(alarms) == 2

    def test_registration_alarm_trigger_values(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_deadline=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        triggers = sorted([a["TRIGGER"].dt for a in alarms])
        expected_7d = datetime.datetime(2027, 3, 25, 0, 0, tzinfo=datetime.timezone.utc)
        expected_1d = datetime.datetime(2027, 3, 31, 0, 0, tzinfo=datetime.timezone.utc)
        assert triggers == [expected_7d, expected_1d]

    def test_deposit_deadline_produces_one_alarm(self):
        auction = _make_auction(
            registration_deadline=None,
            deposit_deadline=datetime.date(2027, 4, 10),
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        assert len(alarms) == 1

    def test_deposit_alarm_trigger_value(self):
        auction = _make_auction(
            registration_deadline=None,
            deposit_deadline=datetime.date(2027, 4, 10),
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarm = [c for c in event.walk() if c.name == "VALARM"][0]
        expected = datetime.datetime(2027, 4, 9, 0, 0, tzinfo=datetime.timezone.utc)
        assert alarm["TRIGGER"].dt == expected

    def test_both_deadlines_produce_three_alarms(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_deadline=datetime.date(2027, 4, 10),
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        assert len(alarms) == 3

    def test_no_deadlines_no_alarms(self):
        auction = _make_auction(
            registration_deadline=None,
            deposit_deadline=None,
        )
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        assert alarms == []

    def test_alarm_action_is_display(self):
        auction = _make_auction(registration_deadline=datetime.date(2027, 4, 1))
        cal = Calendar.from_ical(auctions_to_ical([auction]))
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        alarms = [c for c in event.walk() if c.name == "VALARM"]
        for alarm in alarms:
            assert str(alarm["ACTION"]) == "DISPLAY"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ical_export.py::TestValarms -v`
Expected: FAIL — no alarms generated

- [ ] **Step 3: Implement VALARM generation**

Replace the full contents of `src/tdc_auction_calendar/exporters/ical.py` with:

```python
"""iCalendar exporter — converts Auction models to RFC 5545 .ics bytes."""

from __future__ import annotations

import datetime

from icalendar import Alarm, Calendar, Event

from tdc_auction_calendar.models.auction import Auction


def _build_description(auction: Auction) -> str:
    """Build human-readable DESCRIPTION from non-null fields."""
    lines: list[str] = []
    if auction.registration_deadline is not None:
        lines.append(f"Registration deadline: {auction.registration_deadline}")
    if auction.deposit_amount is not None:
        lines.append(f"Deposit amount: ${auction.deposit_amount:,.2f}")
    if auction.deposit_deadline is not None:
        lines.append(f"Deposit deadline: {auction.deposit_deadline}")
    if auction.property_count is not None:
        lines.append(f"Properties: {auction.property_count}")
    if auction.source_url is not None:
        lines.append(f"Source: {auction.source_url}")
    return "\n".join(lines)


def _make_alarm(trigger_dt: datetime.datetime, description: str) -> Alarm:
    """Create a DISPLAY VALARM with an absolute trigger time."""
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", description)
    alarm.add("trigger", trigger_dt)
    return alarm


def _add_alarms(event: Event, auction: Auction) -> None:
    """Add VALARMs for registration and deposit deadlines."""
    if auction.registration_deadline is not None:
        reg_dt = datetime.datetime.combine(
            auction.registration_deadline, datetime.time.min, tzinfo=datetime.timezone.utc
        )
        event.add_component(_make_alarm(
            reg_dt - datetime.timedelta(days=7),
            f"Registration in 7 days: {auction.county} {auction.state}",
        ))
        event.add_component(_make_alarm(
            reg_dt - datetime.timedelta(days=1),
            f"Registration tomorrow: {auction.county} {auction.state}",
        ))
    if auction.deposit_deadline is not None:
        dep_dt = datetime.datetime.combine(
            auction.deposit_deadline, datetime.time.min, tzinfo=datetime.timezone.utc
        )
        event.add_component(_make_alarm(
            dep_dt - datetime.timedelta(days=1),
            f"Deposit due tomorrow: {auction.county} {auction.state}",
        ))


def _build_event(auction: Auction) -> Event:
    """Build a VEVENT from an Auction model."""
    event = Event()
    event.add("summary", f"{auction.county} {auction.state} Tax {auction.sale_type.title()} Sale")
    event.add("dtstart", auction.start_date)
    event.add("dtend", auction.end_date or auction.start_date + datetime.timedelta(days=1))
    event.add("uid", f"{auction.state}-{auction.county}-{auction.start_date}-{auction.sale_type}@tdc-auction-calendar")
    description = _build_description(auction)
    if description:
        event.add("description", description)
    if auction.source_url:
        event.add("url", auction.source_url)
    _add_alarms(event, auction)
    return event


def auctions_to_ical(auctions: list[Auction]) -> bytes:
    """Convert a list of Auction models to iCalendar bytes."""
    cal = Calendar()
    cal.add("prodid", "-//TDC Auction Calendar//EN")
    cal.add("version", "2.0")
    for auction in auctions:
        cal.add_component(_build_event(auction))
    return cal.to_ical()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ical_export.py::TestValarms -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Run all iCal tests**

Run: `uv run pytest tests/test_ical_export.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/exporters/ical.py tests/test_ical_export.py
git commit -m "feat: iCal VALARM triggers for deadlines (issue #18)"
```

## Chunk 2: Query Helper and CLI Integration

### Task 4: `query_auctions` filter helper

**Files:**
- Modify: `src/tdc_auction_calendar/exporters/ical.py`
- Modify: `tests/test_ical_export.py`

These tests use the `db_session` fixture from `tests/conftest.py` (in-memory SQLite with tables created).

- [ ] **Step 1: Write failing tests for `query_auctions`**

Add to `tests/test_ical_export.py`:

```python
import datetime

from tdc_auction_calendar.exporters.ical import query_auctions
from tdc_auction_calendar.models.auction import AuctionRow


def _future(days=365):
    return datetime.date.today() + datetime.timedelta(days=days)


def _past(days=30):
    return datetime.date.today() - datetime.timedelta(days=days)


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


class TestQueryAuctions:
    def test_returns_future_auctions_by_default(self, db_session):
        _insert_auction(db_session, start_date=_future())
        _insert_auction(db_session, county="Broward", start_date=_past())
        result = query_auctions(db_session)
        assert len(result) == 1
        assert result[0].county == "Miami-Dade"

    def test_filter_by_single_state(self, db_session):
        _insert_auction(db_session, state="FL")
        _insert_auction(db_session, state="TX", county="Harris")
        result = query_auctions(db_session, states=["FL"])
        assert len(result) == 1
        assert result[0].state == "FL"

    def test_filter_by_multiple_states(self, db_session):
        _insert_auction(db_session, state="FL")
        _insert_auction(db_session, state="TX", county="Harris")
        _insert_auction(db_session, state="GA", county="Fulton", start_date=_future(days=400))
        result = query_auctions(db_session, states=["FL", "TX"])
        assert len(result) == 2
        assert {a.state for a in result} == {"FL", "TX"}

    def test_filter_by_sale_type(self, db_session):
        _insert_auction(db_session, sale_type="deed")
        _insert_auction(db_session, county="Broward", sale_type="lien")
        result = query_auctions(db_session, sale_type="lien")
        assert len(result) == 1
        assert result[0].sale_type == "lien"

    def test_filter_by_date_range(self, db_session):
        near = _future(days=30)
        far = _future(days=400)
        _insert_auction(db_session, start_date=near)
        _insert_auction(db_session, county="Broward", start_date=far)
        cutoff = near + datetime.timedelta(days=5)
        result = query_auctions(db_session, from_date=near, to_date=cutoff)
        assert len(result) == 1
        assert result[0].county == "Miami-Dade"

    def test_to_date_none_means_no_upper_bound(self, db_session):
        _insert_auction(db_session, start_date=_future(days=1000))
        result = query_auctions(db_session, from_date=datetime.date.today())
        assert len(result) == 1

    def test_returns_pydantic_models(self, db_session):
        _insert_auction(db_session)
        result = query_auctions(db_session)
        assert len(result) == 1
        from tdc_auction_calendar.models.auction import Auction
        assert isinstance(result[0], Auction)

    def test_ordered_by_start_date(self, db_session):
        _insert_auction(db_session, county="Later", start_date=_future(days=400))
        _insert_auction(db_session, county="Sooner", start_date=_future(days=30))
        result = query_auctions(db_session)
        assert result[0].county == "Sooner"
        assert result[1].county == "Later"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ical_export.py::TestQueryAuctions -v`
Expected: FAIL — `query_auctions` not defined

- [ ] **Step 3: Implement `query_auctions`**

Add to `src/tdc_auction_calendar/exporters/ical.py`:

Add the following imports at the top of `src/tdc_auction_calendar/exporters/ical.py`:

```python
from sqlalchemy.orm import Session

from tdc_auction_calendar.models.auction import AuctionRow
from tdc_auction_calendar.models.enums import SaleType
```

Then add this function after `auctions_to_ical`:

```python
def query_auctions(
    session: Session,
    states: list[str] | None = None,
    sale_type: SaleType | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
) -> list[Auction]:
    """Query auctions from the DB with optional filters, return Pydantic models."""
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

    rows = query.order_by(AuctionRow.start_date).all()
    return [Auction.model_validate(r, from_attributes=True) for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ical_export.py::TestQueryAuctions -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/exporters/ical.py tests/test_ical_export.py
git commit -m "feat: query_auctions filter helper (issue #18)"
```

### Task 5: CLI `export ical` command

**Files:**
- Modify: `src/tdc_auction_calendar/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Remove old stub test and write new CLI tests**

First, delete `test_export_ical_stub` from `TestExportStubs` in `tests/test_cli.py` (the command will no longer be a stub).

Then add to `tests/test_cli.py` (uses existing `cli_db` fixture and `_future_date` helper):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::TestExportIcal -v`
Expected: FAIL — the stub exits with code 1

- [ ] **Step 3: Replace the CLI stub with real implementation**

Replace the `export_ical` function in `src/tdc_auction_calendar/cli.py`:

```python
@export_app.command("ical")
def export_ical(
    state: list[str] | None = typer.Option(None, "--state", help="Filter by state code (repeatable)"),
    sale_type: SaleType | None = typer.Option(None, "--sale-type", help="Filter by sale type"),
    from_date: str | None = typer.Option(None, "--from-date", help="Start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, "--to-date", help="End date (YYYY-MM-DD)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
    """Export auctions to iCalendar (.ics) format."""
    import sys

    from tdc_auction_calendar.exporters.ical import auctions_to_ical, query_auctions

    if not _check_db_exists():
        console.print("[red]Database not found.[/red] Run `tdc-auction-calendar collect` first.")
        raise typer.Exit(1)

    # Parse dates
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
        )
    finally:
        session.close()

    ical_bytes = auctions_to_ical(auctions)

    if output:
        with open(output, "wb") as f:
            f.write(ical_bytes)
    else:
        sys.stdout.buffer.write(ical_bytes)

    typer.echo(f"Exported {len(auctions)} auction(s).", err=True)
```

Note: Uses `typer.echo(..., err=True)` instead of `console.print(..., err=True)` so the count message is properly captured by Typer's test runner on stderr.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py::TestExportIcal -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/cli.py tests/test_cli.py
git commit -m "feat: CLI export ical command (issue #18)"
```

### Task 6: Round-trip validation test

**Files:**
- Modify: `tests/test_ical_export.py`

This is the acceptance criteria test — generate a full calendar, parse it back, verify everything.

- [ ] **Step 1: Write round-trip test**

Add to `tests/test_ical_export.py`:

```python
class TestRoundTrip:
    def test_full_round_trip(self):
        """Acceptance: output validates via icalendar parse round-trip."""
        auctions = [
            _make_auction(
                state="FL", county="Miami-Dade",
                start_date=datetime.date(2027, 4, 15),
                end_date=datetime.date(2027, 4, 17),
                sale_type="deed",
                registration_deadline=datetime.date(2027, 4, 1),
                deposit_deadline=datetime.date(2027, 4, 10),
                deposit_amount=Decimal("5000.00"),
                property_count=150,
                source_url="https://example.com/auction",
            ),
            _make_auction(
                state="TX", county="Harris",
                start_date=datetime.date(2027, 6, 1),
                end_date=None,
                sale_type="lien",
                registration_deadline=None,
                deposit_deadline=None,
                source_url=None,
            ),
        ]
        ical_bytes = auctions_to_ical(auctions)

        # Parse round-trip
        cal = Calendar.from_ical(ical_bytes)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 2

        # First event — full fields
        fl = next(e for e in events if "Miami-Dade" in str(e["SUMMARY"]))
        assert str(fl["SUMMARY"]) == "Miami-Dade FL Tax Deed Sale"
        assert fl["DTSTART"].dt == datetime.date(2027, 4, 15)
        assert fl["DTEND"].dt == datetime.date(2027, 4, 17)
        assert "URL" in fl
        alarms = [c for c in fl.walk() if c.name == "VALARM"]
        assert len(alarms) == 3  # 2 registration + 1 deposit

        # Second event — minimal fields
        tx = next(e for e in events if "Harris" in str(e["SUMMARY"]))
        assert tx["DTEND"].dt == datetime.date(2027, 6, 2)  # start + 1 day
        assert "URL" not in tx
        tx_alarms = [c for c in tx.walk() if c.name == "VALARM"]
        assert len(tx_alarms) == 0

    def test_multiple_auctions_same_fields(self):
        """Multiple events with unique UIDs."""
        a1 = _make_auction(state="FL", county="Miami-Dade", start_date=datetime.date(2027, 4, 15))
        a2 = _make_auction(state="FL", county="Broward", start_date=datetime.date(2027, 5, 1))
        cal = Calendar.from_ical(auctions_to_ical([a1, a2]))
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        uids = [str(e["UID"]) for e in events]
        assert len(set(uids)) == 2  # unique UIDs
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_ical_export.py::TestRoundTrip -v`
Expected: PASS (these test already-implemented functionality)

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_ical_export.py
git commit -m "test: round-trip validation for iCal export (issue #18)"
```
