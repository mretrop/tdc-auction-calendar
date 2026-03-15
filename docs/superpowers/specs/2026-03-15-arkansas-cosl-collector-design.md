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

**Update:**
- `_URL` → `"https://www.cosl.org/Home/Contents"`
- `_fetch()` → fetch markdown via `client.scrape()`, parse with `parse_catalog()`, normalize results

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
- Confidence score: `0.85`
- `normalize()` structure
- Orchestrator registration

### Parsing Logic Detail

The markdown has a repeating structure:
```
<date line>
<county link line>
<catalog link line>
<county link line>
<catalog link line>
...
<next date line>
```

The parser maintains a `current_date` variable. When a date line is matched, it updates `current_date`. When a county line is matched, it emits a record pairing `current_date` with the county name (title-cased). Counties appearing before any date are skipped.

## Testing

### File: `tests/collectors/state_agencies/test_arkansas.py`

**Unit tests (no mocks):**
- `test_parse_catalog_basic` — sample markdown with one date/one county → correct output
- `test_parse_catalog_multi_county_date` — one date with multiple counties → one record per county
- `test_parse_catalog_county_title_case` — `"ST FRANCIS"` → `"St Francis"`, `"HOT SPRING"` → `"Hot Spring"`
- `test_parse_catalog_empty` — empty string or no matches → empty list

**Integration test (mock ScrapeClient):**
- `test_fetch_returns_auctions` — mock `client.scrape()` with fixture markdown, verify Auction objects
- `test_collect_dedup` — verify dedup via `collect()`

**Fixture:** trimmed version of `data/research/sub/cosl_catalog.md` with 3-4 dates and varying county counts.

## No New Dependencies

The rewrite uses only stdlib (`re`, `datetime`) plus existing project imports. No new packages needed.
