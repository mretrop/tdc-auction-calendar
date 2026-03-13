# CSV + JSON Exporters — Design Spec

**Issue:** #19 — [M3] CSV + JSON exporters
**Date:** 2026-03-13

## Overview

Add CSV and JSON export formats for auction records, plus a shared query/filter layer that all exporters (including the existing iCal exporter) use.

## Shared Query Layer — `exporters/filters.py`

Extract `query_auctions()` from `ical.py` into a new `filters.py` module so all exporters share one DB query path.

```python
def query_auctions(
    session: Session,
    states: list[str] | None = None,
    sale_type: SaleType | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    upcoming_only: bool = False,
) -> list[Auction]:
```

- Existing filters: states (case-insensitive), sale_type, date range (defaults to today onwards if no from_date)
- New filter: `upcoming_only` — filters to `status == AuctionStatus.upcoming`
- Converts ORM rows to Pydantic models via `Auction.model_validate(row, from_attributes=True)`
- Update `ical.py` to import from `filters.py` instead of defining its own query function

## CSV Exporter — `exporters/csv_export.py`

### Interface

```python
def auctions_to_csv(auctions: list[Auction]) -> str:
```

Returns a CSV string with header row.

### Columns (in order)

state, county, sale_type, start_date, end_date, registration_deadline, deposit_amount, interest_rate, property_count, vendor, confidence_score, source_url

Curated subset for spreadsheet use. Intentionally excludes: status (filterable via `--upcoming-only`), source_type, deposit_deadline, min_bid, notes. These are available in the JSON export which includes all fields.

### Format Details

- ISO 8601 dates (YYYY-MM-DD)
- None/null fields written as empty strings
- Uses `csv.DictWriter` with `io.StringIO`
- Must round-trip cleanly through `csv.DictReader`

## JSON Exporter — `exporters/json_export.py`

### Interface

```python
def auctions_to_json(auctions: list[Auction], compact: bool = False) -> str:
```

Returns a JSON string.

### Format Details

- Output: JSON array of auction objects
- Uses Pydantic `.model_dump(mode="json")` for correct serialization of dates, Decimals, enums
- `compact=False` (default): 2-space indented
- `compact=True`: single-line, no extra whitespace
- All Auction fields included (matches Pydantic schema)

## CLI Commands

Replace existing stub commands in `cli.py`.

### `export csv`

```
--state         Filter by state(s), repeatable
--sale-type     Filter by sale type
--from-date     Start date (YYYY-MM-DD)
--to-date       End date (YYYY-MM-DD)
--upcoming-only Only include upcoming auctions
-o / --output   Output file (default: stdout)
```

### `export json`

Same options as CSV, plus:

```
--compact       Single-line output (no indentation)
```

### Shared CLI Pattern

Both commands follow the same workflow as `export ical`:
1. Check DB exists
2. Parse date options
3. Query auctions via shared `query_auctions()`
4. Convert to format
5. Write to file (`"w"` text mode, not `"wb"`) or stdout
6. Echo summary to stderr

## Acceptance Criteria

- CSV round-trips through `csv.DictReader` cleanly
- JSON validates against the Pydantic `Auction` model
- Both exporters share `query_auctions()` from `filters.py`
- Existing iCal exporter updated to use shared `query_auctions()`
- iCal export behavior unchanged after refactor

## Notes

- Tests for these exporters are tracked separately in issue #21
- `exporters/__init__.py` is currently empty; no changes needed (modules imported directly in CLI)
