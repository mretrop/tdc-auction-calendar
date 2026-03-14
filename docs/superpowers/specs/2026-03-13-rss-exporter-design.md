# RSS Exporter — Design Spec

**Issue:** #20 — [M3] RSS exporter
**Date:** 2026-03-13

## Overview

Add RSS 2.0 feed export for auction records, following the same patterns as CSV/JSON/iCal exporters.

## RSS Exporter — `exporters/rss.py`

### Interface

```python
def auctions_to_rss(auctions: list[Auction], title: str = "Tax Auction Calendar") -> str:
```

Returns valid RSS 2.0 XML string. Uses `xml.etree.ElementTree` for XML generation and `email.utils.format_datetime` for RFC 822 dates (both stdlib — no new dependency). HTML in `<description>` uses `html.escape()` for safety.

### Feed Structure

- `<rss version="2.0">` root element
- `<channel>` with:
  - `<title>`: passed via `title` parameter
  - `<description>`: "Tax deed auction dates aggregated from county and state sources"
  - `<link>`: "https://github.com/mretrop/tdc-auction-calendar"
  - `<lastBuildDate>`: current UTC time in RFC 822 format
- Each auction becomes an `<item>` with:
  - `<title>`: `"{county} {state} Tax {sale_type.title()} Sale — {start_date}"`
  - `<description>`: HTML snippet with key fields (registration deadline, deposit amount, vendor, source link)
  - `<pubDate>`: `start_date` in RFC 822 format
  - `<guid isPermaLink="false">`: `{state}-{county}-{start_date}-{sale_type}` (stable across runs, matches iCal UID pattern)
  - `<link>`: `source_url` if available

## CLI Command

Replace the `export rss` stub in `cli.py`. Uses shared helpers (`_parse_dates`, `_query_export_auctions`, `_write_output`).

### Options

```
--state         Filter by state(s), repeatable
--sale-type     Filter by sale type
--from-date     Start date (YYYY-MM-DD)
--to-date       End date (YYYY-MM-DD)
--days N        Shortcut: auctions from last N days (overrides --from-date)
--upcoming-only Only include upcoming auctions
-o / --output   Output file (default: stdout)
```

### `--days` Behavior

- Computes `from_date = today - N days`
- If both `--days` and `--from-date` are provided, `--days` wins
- Feed title: `"Tax Auction Calendar — {state}"` when filtered by exactly one state, generic title otherwise (multiple states or no filter)

## Acceptance Criteria

- Valid RSS 2.0 XML (parseable by `xml.etree.ElementTree`)
- guid is stable (same auction = same guid across runs)
- State filter works
- `--days` convenience flag works

## Notes

- Tests for this exporter are tracked separately in issue #21
- No new dependencies — uses stdlib `xml.etree.ElementTree`
