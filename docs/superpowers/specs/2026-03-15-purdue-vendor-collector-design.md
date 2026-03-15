# Purdue Vendor Collector Design

**Issue:** #46 — [M5] Collector: Purdue Texas tax sales (pbfcm.com)
**Date:** 2026-03-15

## Summary

Build a collector for `pbfcm.com/taxsale.html` that extracts exact sale dates from per-county PDF documents. The site lists ~17 Texas counties with upcoming tax foreclosure sales, each linking to a PDF containing the sale date and property list.

## Architecture

### Two-Phase Fetch + Extract

1. **HTML phase:** Use `ScrapeClient` to fetch the main listing page. Parse the returned markdown to extract `(county_name, pdf_url)` tuples using regex on the list structure.
2. **PDF phase:** Download each PDF via httpx to `data/research/purdue_pdfs/`. Extract text with `pypdf`, parse sale dates with regex. Combine with county name to produce `Auction` objects via `normalize()`.

### File Structure

```
src/tdc_auction_calendar/collectors/vendors/
    __init__.py
    purdue.py
tests/collectors/vendors/
    test_purdue.py
tests/fixtures/
    sample_purdue_sale.pdf
data/research/purdue_pdfs/        # cached PDF downloads (covered by `data/` rule in .gitignore)
```

New `collectors/vendors/` category for third-party vendor sites (Purdue, and future collectors like MVBA Law #48).

## Enum Changes

### SourceType

Add `VENDOR = "vendor"` to `SourceType` in `models/enums.py`. Purdue is a law firm, not a county website — using `COUNTY_WEBSITE` would be misleading.

### Vendor

Add `PURDUE = "Purdue, Brandon, Fielder, Collins & Mott"` to `Vendor` in `models/enums.py`, consistent with existing vendor enum pattern.

## Collector Implementation

### PurdueCollector

- Extends `BaseCollector`
- `name` = `"purdue_vendor"`
- `source_type` = `SourceType.VENDOR`
- `confidence_score` = `0.80`

### `_fetch()` Flow

1. `ScrapeClient.scrape("https://www.pbfcm.com/taxsale.html")` returns page markdown
2. Parse markdown with regex to extract county names and PDF URLs from the nested list structure:
   - Top-level `* COUNTY NAME` entries
   - Nested `[link text](docs/taxdocs/sales/XX-XXXXcountytaxsale.pdf)` entries
3. For each PDF URL:
   - Download to `data/research/purdue_pdfs/{filename}` (skip if already exists and less than 7 days old)
   - Extract text with `pypdf.PdfReader`
   - Call `normalize()` with raw dict `{"county": ..., "date": ..., "pdf_url": ...}`
4. Return list of `Auction` objects

### `normalize()` Method

Implements the `BaseCollector` abstract method. Takes a raw dict with keys `county`, `date`, `pdf_url` and returns a validated `Auction` object with the field mappings described in Data Mapping below.

### HTML Parsing

Regex on markdown list structure. County names come from the top-level list items (e.g., `* BRAZORIA COUNTY`). PDF URLs come from nested links. County name is stripped of "COUNTY" suffix and title-cased.

**Markdown format note:** Both Cloudflare and Crawl4AI fetchers produce standard markdown with `*` list markers and `[text](url)` links. The regex should handle minor whitespace/formatting differences between fetchers.

### PDF Date Parsing

Regex patterns tried in order (most specific first):

1. `(?:Sale Date|Date of Sale)[:\s]+(\w+ \d{1,2},?\s*\d{4})` — contextual "sale date" match
2. `((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4})` — month-name date pattern (constrained to real month names)
3. `(\d{1,2}/\d{1,2}/\d{4})` — numeric format

If no date is found, log a warning and skip the county.

### PDF Caching

PDFs are downloaded to `data/research/purdue_pdfs/`. Files are re-downloaded if older than 7 days (simple TTL based on file modification time). This directory is already covered by the existing `.gitignore`.

### Rate Limiting for PDF Downloads

PDF downloads use httpx directly (not ScrapeClient, which is designed for HTML page scraping). Add a small delay (0.5s) between PDF downloads to avoid hammering the server.

## Data Mapping

| Field | Value |
|-------|-------|
| `state` | `"TX"` |
| `county` | From HTML, title-cased, "COUNTY" suffix removed |
| `start_date` | Parsed from PDF content |
| `end_date` | `None` |
| `sale_type` | `SaleType.DEED` |
| `status` | `AuctionStatus.UPCOMING` |
| `source_type` | `SourceType.VENDOR` |
| `source_url` | Full PDF URL |
| `confidence_score` | `0.80` |
| `vendor` | `Vendor.PURDUE` (StrEnum auto-coerces to str, matching `Auction.vendor: str \| None`) |

### Multi-Precinct Counties

Fort Bend and Harris have multiple precinct PDFs. Each produces its own `Auction` record with the same county name. Different precincts may have different sale dates, producing multiple valid records per county. Same-date precincts collapse via dedup key `(state, county, start_date, sale_type)`, which is correct — one county sale event per date.

## Error Handling

- **Listing page returns no links:** Log warning, return empty list (don't raise — other collectors should still run).
- **Individual PDF download fails:** Log warning with county name and HTTP status, skip that county, continue processing remaining PDFs.
- **pypdf fails to extract text:** Log warning, skip that county.
- **No date found in PDF text:** Log warning with county name, skip that county.
- **All PDFs fail:** Log error with failure count. Return whatever records were successfully parsed (may be empty list).

## Dependencies

- **New:** `pypdf` added to `pyproject.toml`
- **Existing:** `httpx` (for PDF downloads), `ScrapeClient` (for HTML fetch)

## Registration

- Add `PurdueCollector` to `COLLECTORS` dict in `collectors/orchestrator.py`
- Export from `collectors/vendors/__init__.py`

## Testing

In `tests/collectors/vendors/test_purdue.py`:

1. **HTML parsing** — Feed sample markdown into link extraction, assert correct `(county, pdf_url)` tuples
2. **PDF date parsing** — Create test PDF fixture with known sale date, verify correct extraction
3. **Date regex patterns** — Test various date format strings directly against regex (including edge cases: ordinals, missing commas, numeric format)
4. **Normalization** — Assert `Auction` fields are correct for given inputs
5. **Multi-precinct** — Verify separate records with same county name and different dates produce multiple records
6. **Error cases** — PDF with no date logs warning and is skipped; unparseable PDF is skipped gracefully

Test fixture: `tests/fixtures/sample_purdue_sale.pdf` with predictable sale date text. No live site integration tests.
