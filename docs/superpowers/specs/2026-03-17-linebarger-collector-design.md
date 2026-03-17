# Linebarger Collector Design

**Issue**: #58 — Add Linebarger collector for TX/PA tax sales
**Date**: 2026-03-17
**Status**: Approved

## Summary

Add a `LinebargerCollector` that fetches tax sale auction dates from the Linebarger Goggan Blair & Sampson portal (`taxsales.lgbs.com`) via its REST API. Covers TX and PA counties.

## Approach

The Linebarger site is an AngularJS SPA backed by a REST API. Rather than rendering the SPA with Crawl4AI, we call the API directly with plain `httpx` — the same pattern as `Bid4AssetsCollector`.

**Key discovery**: The `/api/filter_bar/?limit=1000` endpoint returns all active auction listings in a single paginated JSON response, including county, state, sale date, status, and precinct.

## API Details

### Primary endpoint

```
GET https://taxsales.lgbs.com/api/filter_bar/?limit=1000
```

**Response structure**:
```json
{
  "count": 62,
  "next": null,
  "previous": null,
  "results": [
    {
      "county": "HARRIS COUNTY",
      "state": "TX",
      "sale_date_only": "2026-04-07",
      "status": "Scheduled for Auction",
      "precinct": "1"
    }
  ]
}
```

**Status values observed**: `"Scheduled for Auction"`, `"Scheduled for Online Auction"`, `"Cancelled"`

### Secondary endpoint (county discovery)

```
GET https://taxsales.lgbs.com/api/sale_counties/
```

Returns all 36 counties with active sales. Not needed for the collector itself (filter_bar includes county data), but useful for validation.

## Data Flow

1. **Fetch**: `httpx.AsyncClient.get()` to `/api/filter_bar/?limit=1000`
2. **Paginate**: If `next` is not null, follow pagination links (unlikely at current volume)
3. **Filter**: Drop entries where `status == "Cancelled"`
4. **Group**: Deduplicate by `(state, county, sale_date_only)` — multiple precincts on the same date in the same county become one Auction
5. **Normalize**: Map each group to an `Auction` Pydantic model

## Field Mapping

| API Field | Auction Field | Transformation |
|-----------|--------------|----------------|
| `state` | `state` | Direct (already 2-letter code) |
| `county` | `county` | Strip " COUNTY" suffix, title-case |
| `sale_date_only` | `start_date` | Parse YYYY-MM-DD |
| `status` | `status` | "Scheduled for Auction" / "Scheduled for Online Auction" → `UPCOMING`, "Cancelled" → filtered out |
| (derived from state) | `sale_type` | TX → `DEED`, PA → `DEED` |
| (constant) | `source_type` | `SourceType.VENDOR` |
| (constant) | `vendor` | `Vendor.LINEBARGER` |
| (derived) | `source_url` | `https://taxsales.lgbs.com/map?area={state}` |
| (constant) | `confidence_score` | `1.0` (direct API data) |
| (not available) | `end_date` | `None` |

## Sale Type Mapping

Linebarger uses its own sale type labels (Sale, Resale, Struck-off, Future sale). These are all sub-categories of tax deed/lien sales, not our `SaleType` enum values. We map based on state:

- **TX** → `SaleType.DEED` (Texas is a deed state)
- **PA** → `SaleType.DEED` (Pennsylvania conducts upset/judicial tax sales — deed state per seed data)

All four Linebarger sale types (Sale, Resale, Struck-off, Future sale) map to the same `SaleType` per state.

## File Changes

### New files

- `src/tdc_auction_calendar/collectors/vendors/linebarger.py` — `LinebargerCollector(BaseCollector)`
- `tests/test_linebarger.py` — unit tests with mocked httpx responses

### Modified files

- `src/tdc_auction_calendar/models/enums.py` — add `LINEBARGER = "Linebarger Goggan Blair & Sampson"` to `Vendor`
- `src/tdc_auction_calendar/collectors/orchestrator.py` — add `"linebarger": LinebargerCollector` to `COLLECTORS`
- `src/tdc_auction_calendar/collectors/vendors/__init__.py` — export `LinebargerCollector`
- `src/tdc_auction_calendar/collectors/__init__.py` — re-export `LinebargerCollector`

## Edge Cases

- **Pagination**: Current data fits in one page (62 results, limit=1000). If count exceeds limit, follow `next` URLs in a loop.
- **Future sales**: Include if `sale_date_only` is present. Skip if date is null/empty.
- **County name normalization**: Strip " COUNTY" suffix, title-case. Handles multi-word names like "JIM HOGG COUNTY" → "Jim Hogg", "FORT BEND COUNTY" → "Fort Bend".
- **API unavailability**: Raise `ScrapeError` on failure (match Bid4Assets pattern — no retries at collector level).

## Testing Strategy

- Mock httpx responses with realistic JSON fixtures
- Test cancelled-entry filtering
- Test county name normalization (single word, multi-word, edge cases)
- Test deduplication (same county + date + different precincts → one Auction)
- Test pagination (mock `next` URL scenario)
- Test sale type mapping (TX → DEED, PA → DEED)
