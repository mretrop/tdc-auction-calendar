# Arkansas COSL Collector — Regex-Based Rewrite

**Issue:** #47
**Date:** 2026-03-15
**Status:** Design approved

## Summary

Replace the existing `ArkansasCollector` (Cloudflare JSON extraction against `cosl.org` root) with a deterministic regex-based parser targeting the COSL catalog page at `https://www.cosl.org/Home/Contents`. This eliminates LLM extraction cost, improves reliability, and correctly extracts all county-date pairs from the structured markdown.

## What Changes

### File: `src/tdc_auction_calendar/collectors/state_agencies/arkansas.py`

**Remove:**
- `ArkansasAuctionRecord` Pydantic schema (no longer needed)
- `json_options` / `_PROMPT` (no LLM extraction)
- `ExtractionError` import (no longer raised)

**Update:**
- `_URL` → `"https://www.cosl.org/Home/Contents"` (also changes `source_url` on emitted Auctions)
- `_fetch()` → fetch markdown via `result.fetch.markdown`, parse with `parse_catalog()`, normalize results

**Add:**
- `parse_catalog(markdown: str) -> list[dict]` — walks lines sequentially:
  - Date regex: `\d{1,2}/\d{1,2}/\d{4}` — matches lines like `7/14/2026 12:00 AM`
  - County regex: `\[\s*([A-Z ]+?)\s*\]\(#\)` — matches `[ SEVIER](#)`
  - Each county found after a date line is paired with that date
  - Returns `[{"sale_date": "2026-07-14", "county": "Prairie"}, ...]`
- County names are title-cased (e.g., `"ST FRANCIS"` → `"St Francis"`, `"HOT SPRING"` → `"Hot Spring"`)

**Unchanged:**
- Class name: `ArkansasCollector`
- Collector name: `"arkansas_state_agency"`
- Source type: `SourceType.STATE_AGENCY`
- Confidence score: `0.85` (kept despite deterministic parsing — page structure could change without warning)
- `normalize()` structure — `sale_type` defaults to `"deed"` via `raw.get("sale_type", "deed")` since `parse_catalog()` output omits it
- Orchestrator registration

### Parsing Logic Detail

The markdown has a repeating structure. The first entry (past sales) includes location info between date and county; subsequent entries (upcoming sales) omit it. The parser handles both because it simply skips non-matching lines:

```
# Example input/output:

Input markdown:
  7/14/2026 12:00 AM
  [ PRAIRIE](#)
  [  View Catalog](...)
  [ LONOKE](#)
  [  View Catalog](...)

Output:
  [
    {"sale_date": "2026-07-14", "county": "Prairie"},
    {"sale_date": "2026-07-14", "county": "Lonoke"}
  ]
```

The parser maintains a `current_date` variable. When a date line is matched, it updates `current_date`. When a county line is matched, it emits a record pairing `current_date` with the county name (title-cased). Counties appearing before any date are skipped.

### Error Handling in `_fetch()`

- Access markdown via `result.fetch.markdown or ""` (defensive against None)
- If `parse_catalog()` returns an empty list from non-empty markdown, log a warning (possible page structure change)
- Per-record normalization errors are logged and skipped (same pattern as current code, though unlikely with deterministic input)

## Testing

### File: `tests/collectors/state_agencies/test_arkansas.py`

**Unit tests (no mocks):**
- `test_parse_catalog_basic` — one date/one county → correct output
- `test_parse_catalog_multi_county_date` — one date with multiple counties → one record per county
- `test_parse_catalog_county_title_case` — `"ST FRANCIS"` → `"St Francis"`, `"HOT SPRING"` → `"Hot Spring"`
- `test_parse_catalog_empty` — empty string or no matches → empty list
- `test_parse_catalog_date_format` — verify `M/D/YYYY` correctly converts to ISO `YYYY-MM-DD` (e.g., `3/5/2026` → `2026-03-05`)
- `test_parse_catalog_counties_before_date_skipped` — county lines before any date line are ignored
- `test_parse_catalog_duplicate_county_different_dates` — SEVIER under two different dates produces two records

**Integration test (mock ScrapeClient):**
- `test_fetch_returns_auctions` — mock `client.scrape()` with fixture markdown, verify Auction objects including `source_url`
- `test_collect_dedup` — verify dedup via `collect()`

**Fixture:** trimmed version of `data/research/sub/cosl_catalog.md` including the first entry (SEVIER 3/5/2026 with location info) plus 2-3 upcoming dates with varying county counts.

## No New Dependencies

The rewrite uses only stdlib (`re`, `datetime`) plus existing project imports. No new packages needed.
