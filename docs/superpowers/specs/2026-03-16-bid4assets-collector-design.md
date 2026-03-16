# Bid4Assets Collector Design

**Issue:** #51
**Date:** 2026-03-16
**Status:** Approved

## Overview

A vendor collector that scrapes the Bid4Assets auction calendar page to extract tax sale auction dates across multiple states (CA, NV, PA, WA, and others). Uses Crawl4AI with `UNDETECTED` stealth to bypass Akamai bot protection on the calendar page.

## Architecture

### Collector: `Bid4AssetsCollector`

- **File:** `src/tdc_auction_calendar/collectors/vendors/bid4assets.py`
- **Superclass:** `BaseCollector`
- **Source type:** `SourceType.VENDOR`
- **Vendor:** `Vendor.BID4ASSETS` (already in enum)
- **Confidence score:** 0.85 (structured vendor data but stealth-based fetch is less reliable than direct API access)

### Fetching Strategy

- **Target URL:** `https://www.bid4assets.com/auctionCalendar`
- **Fetcher:** Crawl4AI with `StealthLevel.UNDETECTED` (Akamai protection)
- **Known risk:** Prior research (2026-03-14) found Bid4Assets blocked by Akamai. The user has opted to attempt the calendar page with UNDETECTED stealth. If Akamai blocks it, the collector logs a warning and returns an empty list — a future iteration can add storefront URL fallback (issue #51 documents the `/storefront/{CountyName}{MonthYear}` pattern).
- **Magic mode concern:** Crawl4AI enables `magic` mode when stealth is not `OFF`. If magic mode causes issues (as it did with RealAuction), the implementation should test with and without it and adjust accordingly.

**Pagination:** The calendar is a JS carousel showing 3 months at a time.
- **Primary:** Check if the calendar accepts URL parameters (e.g., `?startMonth=7&year=2026`) for direct access to different month windows — this is more reliable and testable.
- **Fallback:** Use Crawl4AI's `js_code` to click the "next" arrow and `wait_for` to capture updated content.
- Two page loads cover ~6 months of upcoming auctions.

### HTML Parsing

Deterministic BeautifulSoup parsing — no LLM extraction needed.

**Auction entry structure** (from observed calendar):
- **Title:** `"{County} County, {ST} Tax Defaulted Properties Auction"`
- **Date range:** `"May 8th - 12th"` or `"April 8th - 8th"`
- **Link (optional):** href to storefront page

**Extraction steps:**
1. BeautifulSoup finds auction entry elements in the calendar grid
2. Regex extracts county name and state abbreviation from title
3. Date parser handles ordinal suffixes ("8th", "23rd") and resolves month from column context
4. Storefront link captured as `source_url` when present

### Sale Type Mapping

Parse sale type from the auction title keywords rather than hardcoding:

| Title keyword | Sale type |
|---------------|-----------|
| "Tax Defaulted" | `SaleType.DEED` |
| "Tax Foreclosed" | `SaleType.DEED` |
| "Tax Title" / "Tax Title/Surplus" | `SaleType.DEED` |
| "Tax Lien" | `SaleType.LIEN` |
| "Repository" | `SaleType.DEED` |
| (no match) | `SaleType.DEED` (default, log warning) |

### Normalization

`normalize(raw: dict) -> Auction` mapping:

| Field | Value |
|-------|-------|
| `state` | 2-letter code from title (e.g., "CA") |
| `county` | County name, stripped of "County" suffix |
| `start_date` | Parsed from date range |
| `end_date` | Parsed from date range; `None` for single-day auctions (matching RealAuction pattern) |
| `sale_type` | Mapped from title keywords (see Sale Type Mapping) |
| `source_type` | `SourceType.VENDOR` |
| `vendor` | `Vendor.BID4ASSETS` |
| `source_url` | Storefront link if present, else calendar URL |
| `confidence_score` | 0.85 |

### Edge Cases

- **Independent cities** (e.g., "Carson City") — no "County" in title; detect by absence
- **Duplicate entries across carousel pages** — Jun appears in both 3-month windows; handled by `BaseCollector.deduplicate()`
- **"To be announced" entries** (e.g., "Tax Sale Dates to be announced soon for August") — skip entries without actual dates
- **Missing state abbreviation** (e.g., slug-style titles like "MonroePATaxApr26") — attempt regex parse of state code from slug; skip and log warning if unparseable
- **Single-day auctions** (e.g., "April 8th - 8th") — set `end_date = None`
- **Cross-month date ranges** — not observed in current data but handle by checking if end day < start day, then incrementing month

### Registration

Add to `COLLECTORS` dict in `collectors/orchestrator.py` (follows `"realauction"` naming convention for vendor collectors):
```python
"bid4assets": Bid4AssetsCollector,
```

## Testing

**Unit tests** in `tests/collectors/vendors/test_bid4assets.py`:

- `test_parse_auction_entry()` — sample HTML snippets -> correct county/state/dates
- `test_normalize()` — raw dict -> valid `Auction` object
- `test_normalize_sale_types()` — verify keyword-to-SaleType mapping for each variant
- `test_edge_cases()` — independent cities, missing state codes, "to be announced" entries, entries without links
- `test_date_parsing()` — ordinal suffixes, same-day ranges ("8th - 8th"), cross-month handling

**Approach:**
- Capture real calendar HTML during development as a test fixture
- Validate `Auction` Pydantic model output (no DB mocking)
- `@pytest.mark.asyncio` for async tests

## File Changes

| File | Change |
|------|--------|
| `src/tdc_auction_calendar/collectors/vendors/bid4assets.py` | New collector |
| `src/tdc_auction_calendar/collectors/vendors/__init__.py` | Export `Bid4AssetsCollector` |
| `src/tdc_auction_calendar/collectors/orchestrator.py` | Register in COLLECTORS dict |
| `tests/collectors/vendors/test_bid4assets.py` | Unit tests |
