# iCalendar Exporter Design

**Issue**: #18 — [M3] iCalendar exporter
**Date**: 2026-03-13
**Approach**: Pure function with `icalendar` library

## Overview

Export auction records as RFC 5545 .ics files. A pure function converts filtered `Auction` Pydantic models into iCalendar bytes. The CLI command handles DB querying and output routing.

## Core Export Function

**File**: `src/tdc_auction_calendar/exporters/ical.py`

```python
def auctions_to_ical(auctions: list[Auction]) -> bytes:
```

Takes filtered Pydantic `Auction` objects, returns RFC 5545 bytes.

### Calendar Properties

- `PRODID:-//TDC Auction Calendar//EN`
- `VERSION:2.0`

### VEVENT Mapping

Each auction becomes one VEVENT:

| iCal Field | Source |
|---|---|
| SUMMARY | `"{county} {state} Tax {sale_type} Sale"` (title-cased sale_type) |
| DTSTART / DTEND | All-day events using `date` values. If `end_date` is null, DTEND = `start_date + 1 day` |
| UID | Deterministic: `{state}-{county}-{start_date}-{sale_type}@tdc-auction-calendar` |
| DESCRIPTION | Human-readable text with deposit amount, registration deadline, property count, source URL (only non-null fields) |
| URL | `source_url` if present, otherwise omitted |

### VALARM Rules

Up to 3 alarms, only when the corresponding deadline field is non-null:

- 7 days before `registration_deadline`
- 1 day before `registration_deadline`
- 1 day before `deposit_deadline`

When a deadline is null, the corresponding VALARM(s) are skipped entirely — no fallback to `start_date`.

## Filtering — Shared Query Helper

```python
def query_auctions(
    session: Session,
    states: list[str] | None = None,
    sale_type: SaleType | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[Auction]:
```

- Queries `AuctionRow`, applies filters, converts to Pydantic `Auction` models
- `states` accepts a list for multi-state filtering (e.g., `["FL", "TX"]`)
- `from_date` defaults to today if not provided (only future auctions)
- Returns results ordered by `start_date`

This keeps the export function pure (no DB awareness) and the query logic reusable by future exporters.

## CLI Integration

Replace the `export ical` stub in `cli.py`:

```python
@export_app.command("ical")
def export_ical(
    state: list[str] | None = Option(None, "--state", help="Filter by state (repeatable)"),
    sale_type: SaleType | None = Option(None, "--sale-type"),
    from_date: str | None = Option(None, "--from-date", help="YYYY-MM-DD"),
    to_date: str | None = Option(None, "--to-date", help="YYYY-MM-DD"),
    output: str | None = Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
```

- Parses dates, calls `query_auctions`, calls `auctions_to_ical`
- Writes to file if `--output` specified, otherwise `sys.stdout.buffer.write()`
- Prints auction count to stderr so it doesn't pollute piped output

## Testing Strategy

- **Round-trip validation**: Generate .ics bytes, parse back with `icalendar.Calendar.from_ical()`, assert events match input
- **VALARM correctness**: Verify negative durations (`-P7D`, `-P1D`) and that alarms are only present when deadlines are set
- **Filter tests**: Verify state, sale_type, and date range filters reduce output (using in-memory SQLite)
- **Edge cases**: Null `end_date` (single-day), null `source_url` (no URL property), all deadlines null (no VALARMs), empty auction list (valid calendar with no events)

## Decisions

- **Output**: Stdout by default, `--output` flag for file — Unix-idiomatic, composable
- **Multi-day auctions**: Single spanning all-day event (not one event per day)
- **Missing deadlines**: Skip VALARMs silently — no fallback to start_date
- **No base class**: Approach A (pure function) chosen over exporter registry pattern — extract shared abstractions when more exporters land
