# Statutory Baseline Collector Design

**Issue:** #7 — [M1] Statutory baseline collector
**Date:** 2026-03-11

## Overview

A Tier 4 collector that generates `Auction` records from seed data alone (no HTTP requests). It reads statutory timing rules from JSON seed files and produces low-confidence auction date windows for every county in every state that holds tax sales.

## Module Structure

**Files:**
- `src/tdc_auction_calendar/collectors/statutory/__init__.py`
- `src/tdc_auction_calendar/collectors/statutory/state_statutes.py`
- `tests/test_statutory_collector.py`

**Class:** `StatutoryCollector(BaseCollector)`

**Properties:**
- `name` -> `"statutory"`
- `source_type` -> `SourceType.STATUTORY`

**Constructor:** `__init__(self, skip_states=None, skip_counties=None)`
- `skip_states`: `set[str]` of 2-char state codes to exclude. Defaults to `DEFAULT_SKIP_STATES` (empty set).
- `skip_counties`: `set[tuple[str, str]]` of `(state, county_name)` tuples to exclude. Defaults to `DEFAULT_SKIP_COUNTIES` (empty set).

**Module-level constants:**
- `DEFAULT_SKIP_STATES: set[str] = set()`
- `DEFAULT_SKIP_COUNTIES: set[tuple[str, str]] = set()`

## Data Sources

Reads directly from JSON files via `SEED_DIR` (no DB dependency):
- `states.json` — state statutory rules including `typical_months`
- `counties.json` — county info with state association
- `vendor_mapping.json` — vendor portal URLs by state/county

## `_fetch()` Logic

1. Load the three seed JSON files.
2. Index vendor mappings by `(state, county)` for O(1) lookup.
3. Set `years = [current_year, current_year + 1]`.
4. For each state in `states.json`:
   - Skip if `state` in `skip_states`.
   - For each county where `county.state == state.state`:
     - Skip if `(state, county_name)` in `skip_counties`.
     - For each month in `state.typical_months`:
       - For each year in `years`:
         - Build a raw dict and call `normalize()`.
5. Return all generated `Auction` objects.

## `normalize()` Method

Takes a raw dict with keys: `state`, `county`, `month`, `year`, `sale_type`, `vendor` (optional), `portal_url` (optional).

Returns an `Auction` with:
- `start_date`: `date(year, month, 1)`
- `end_date`: `date(year, month, last_day)` via `calendar.monthrange`
- `sale_type`: from raw dict (string value from `states.json`, maps to `SaleType` enum)
- `source_type`: `SourceType.STATUTORY`
- `confidence_score`: `0.4`
- `status`: `AuctionStatus.UPCOMING` (default)
- `vendor`: from vendor mapping if present, else `None`
- `source_url`: `portal_url` from vendor mapping if present, else `None`
- All other optional fields: `None`

## Date Generation

For each `typical_month` in a state's rules:
- `start_date` = first day of the month
- `end_date` = last day of the month (via `calendar.monthrange`)
- Generated for both current year and next year
- All records set to `UPCOMING` status regardless of whether the month has passed

## Vendor Enrichment

Vendor mappings are indexed by `(state, county_name)`. When a match exists:
- `vendor` field is set to the vendor name
- `source_url` field is set to the `portal_url`

## Skip Lists

- `DEFAULT_SKIP_STATES` and `DEFAULT_SKIP_COUNTIES` start empty.
- Can be overridden via constructor for testing or when higher-tier collectors are added.
- As we build Tier 1-3 collectors, we update the defaults to avoid generating low-confidence records where better data is available.

## Testing

**File:** `tests/test_statutory_collector.py`

Tests use real seed JSON files (no mocking).

| Test | Description |
|------|-------------|
| Generates 500+ records | `collect()` produces >= 500 auctions from seed data |
| Valid date ranges | `start_date` is 1st, `end_date` is last day, `end_date >= start_date` |
| Correct metadata | All records: `source_type = STATUTORY`, `confidence_score = 0.4` |
| Vendor enrichment | Records with vendor mappings have `vendor` and `source_url` set |
| Skip states | `skip_states={"FL"}` excludes all FL records |
| Skip counties | `skip_counties={("AL", "Jefferson")}` excludes that county |
| Performance | `collect()` < 2 seconds |
| No duplicates | No duplicate dedup keys in output |
| Two-year span | Records cover both current year and next year |

## Acceptance Criteria (from issue)

- [x] Generates >= 500 auction records from seed data alone
- [x] All records have valid date ranges
- [x] `collect()` completes in < 2 seconds (no I/O)
- [x] Extends BaseCollector interface (from #9)
