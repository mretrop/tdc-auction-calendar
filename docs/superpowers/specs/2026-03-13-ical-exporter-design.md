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
| SUMMARY | `"{county} {state} Tax {sale_type} Sale"` (title-cased sale_type, e.g., `"Miami-Dade FL Tax Deed Sale"`) |
| DTSTART / DTEND | All-day events using `date` values. If `end_date` is null, DTEND = `start_date + 1 day` |
| UID | Deterministic: `{state}-{county}-{start_date}-{sale_type}@tdc-auction-calendar` (mirrors DB dedup key) |
| DESCRIPTION | See Description Format below |
| URL | `source_url` if present, otherwise omitted |

### Description Format

Only non-null fields are included, one per line:

```
Registration deadline: 2026-04-01
Deposit amount: $5,000.00
Deposit deadline: 2026-04-10
Properties: 150
Source: https://example.com/auction
```

`deposit_amount` is formatted with `$` prefix and comma thousands separator (`${:,.2f}`). Source URL is intentionally duplicated in both DESCRIPTION and the URL property — some calendar clients don't render the URL field, so including it in the description improves visibility.

### VALARM Rules

Up to 3 alarms, only when the corresponding deadline field is non-null:

- 7 days before `registration_deadline`
- 1 day before `registration_deadline`
- 1 day before `deposit_deadline`

**Implementation**: Use `TRIGGER;VALUE=DATE-TIME` with absolute datetime values computed from the deadline date (e.g., `registration_deadline - 7 days` at midnight UTC). This avoids the default TRIGGER behavior which is relative to DTSTART.

When a deadline is null, the corresponding VALARM(s) are skipped entirely — no fallback to `start_date`. VALARMs for deadlines already in the past at generation time are still emitted — calendar clients handle past alarms gracefully, and the .ics may be generated ahead of time.

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
- `to_date` has no default — omitting it returns all future auctions with no upper bound
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

- Checks DB exists via `_check_db_exists()` (same guard pattern as `list` command)
- Parses dates, calls `query_auctions`, calls `auctions_to_ical`
- Writes to file if `--output` specified, otherwise `sys.stdout.buffer.write()`
- Prints auction count to stderr so it doesn't pollute piped output

## Testing Strategy

- **Round-trip validation**: Generate .ics bytes, parse back with `icalendar.Calendar.from_ical()`, assert events match input
- **VALARM correctness**: Verify absolute `TRIGGER;VALUE=DATE-TIME` values equal `deadline - 7 days` / `deadline - 1 day` (at midnight UTC), and that alarms are only present when deadlines are set
- **Filter tests**: Verify state, sale_type, and date range filters reduce output (using in-memory SQLite)
- **Edge cases**: Null `end_date` (single-day), null `source_url` (no URL property), all deadlines null (no VALARMs), empty auction list (valid calendar with no events)

## Decisions

- **Output**: Stdout by default, `--output` flag for file — Unix-idiomatic, composable
- **Multi-day auctions**: Single spanning all-day event (not one event per day)
- **Missing deadlines**: Skip VALARMs silently — no fallback to start_date
- **No base class**: Approach A (pure function) chosen over exporter registry pattern — extract shared abstractions when more exporters land
