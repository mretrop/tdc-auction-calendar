# Purdue Vendor Collector Design

**Issue:** #46 — [M5] Collector: Purdue Texas tax sales (pbfcm.com)
**Date:** 2026-03-15

## Summary

Build a collector for `pbfcm.com/taxsale.html` that extracts exact sale dates from per-county PDF documents. The site lists ~17 Texas counties with upcoming tax foreclosure sales, each linking to a PDF containing the sale date and property list.

## Architecture

### Two-Phase Fetch + Extract

1. **HTML phase:** Use `ScrapeClient` to fetch the main listing page. Parse the returned markdown to extract `(county_name, pdf_url)` tuples using regex on the list structure.
2. **PDF phase:** Download each PDF via httpx to `data/research/purdue_pdfs/`. Extract text with `pypdf`, parse sale dates with regex. Combine with county name to produce `Auction` objects.

### File Structure

```
src/tdc_auction_calendar/collectors/vendors/
    __init__.py
    purdue.py
tests/collectors/vendors/
    test_purdue.py
tests/fixtures/
    sample_purdue_sale.pdf
data/research/purdue_pdfs/        # cached PDF downloads (gitignored)
```

New `collectors/vendors/` category for third-party vendor sites (Purdue, and future collectors like MVBA Law #48).

## Collector Implementation

### PurdueCollector

- Extends `BaseCollector`
- `name` = `"purdue_vendor"`
- `source_type` = `SourceType.COUNTY_WEBSITE`
- `confidence_score` = `0.80`

### `_fetch()` Flow

1. `ScrapeClient.scrape("https://www.pbfcm.com/taxsale.html")` returns page markdown
2. Parse markdown with regex to extract county names and PDF URLs from the nested list structure:
   - Top-level `* COUNTY NAME` entries
   - Nested `[link text](docs/taxdocs/sales/XX-XXXXcountytaxsale.pdf)` entries
3. For each PDF URL:
   - Download to `data/research/purdue_pdfs/{filename}` (skip if already exists)
   - Extract text with `pypdf.PdfReader`
   - Parse sale date with regex patterns
   - Create `Auction` object
4. Return list of `Auction` objects

### HTML Parsing

Regex on markdown list structure. County names come from the top-level list items (e.g., `* BRAZORIA COUNTY`). PDF URLs come from nested links. County name is stripped of "COUNTY" suffix and title-cased.

### PDF Date Parsing

Regex patterns tried in order (most specific first):

1. `(?:Sale Date|Date of Sale)[:\s]+(\w+ \d{1,2},?\s*\d{4})` — contextual match
2. `(\w+ \d{1,2}(?:st|nd|rd|th)?,?\s*\d{4})` — general date pattern
3. `(\d{1,2}/\d{1,2}/\d{4})` — numeric format

If no date is found, log a warning and skip the county.

### PDF Caching

PDFs are downloaded to `data/research/purdue_pdfs/`. If the file already exists locally, skip the download. This directory should be gitignored.

## Data Mapping

| Field | Value |
|-------|-------|
| `state` | `"TX"` |
| `county` | From HTML, title-cased, "COUNTY" suffix removed |
| `start_date` | Parsed from PDF content |
| `end_date` | `None` |
| `sale_type` | `SaleType.DEED` |
| `status` | `AuctionStatus.UPCOMING` |
| `source_type` | `SourceType.COUNTY_WEBSITE` |
| `source_url` | Full PDF URL |
| `confidence_score` | `0.80` |
| `vendor` | `"Purdue, Brandon, Fielder, Collins & Mott"` |

### Multi-Precinct Counties

Fort Bend and Harris have multiple precinct PDFs. Each produces its own `Auction` record with the same county name. The dedup key `(state, county, start_date, sale_type)` collapses same-date precincts into one record, which is correct — one county sale event.

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
3. **Date regex patterns** — Test various date format strings directly against regex
4. **Normalization** — Assert `Auction` fields are correct for given inputs
5. **Multi-precinct** — Verify separate records with same county name

Test fixture: `tests/fixtures/sample_purdue_sale.pdf` with predictable sale date text. No live site integration tests.
