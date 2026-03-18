# SRI Services Collector Design

**Issue**: #59 — Add SRI Services collector for tax sale properties
**Date**: 2026-03-17
**Status**: Approved

## Summary

Add an `SRICollector` that fetches tax sale auction dates from the SRI Services portal (`sriservices.com/properties`) via its REST API on Azure. Covers CO, IN, LA, TN (and potentially AL, FL, MI as SRI expands).

## Approach

The SRI site is a React SPA backed by an Azure-hosted REST API at `sriservicesusermgmtprod.azurewebsites.net`. Rather than rendering the SPA with Crawl4AI, we call the API directly with plain `httpx` — the same pattern as `LinebargerCollector` and `Bid4AssetsCollector`.

**Key discovery**: The `POST /api/auction/listall` endpoint returns all active auction listings in a single JSON response, including county, state, sale type, auction date, and location details.

## API Details

### Primary endpoint

```
POST https://sriservicesusermgmtprod.azurewebsites.net/api/auction/listall
```

**Headers**:
- `x-api-key: 9f8fd9fe5160294175e1c737567030f495d838a7922a678bc06e0a093910` (public, embedded in client JS bundle)
- `Content-Type: application/json`
- `Accept: application/json`

**Request body**:
```json
{
  "searchText": "",
  "state": "",
  "county": "",
  "propertySaleType": "",
  "auctionStyle": "",
  "saleStatus": "",
  "auctionDateRange": {
    "startDate": "2026-03-17",
    "endDate": "",
    "compareOperator": ">"
  },
  "recordCount": 500,
  "startIndex": 0
}
```

**Response** (JSON array):
```json
[
  {
    "id": 128711,
    "saleType": "Foreclosure",
    "saleTypeCode": "F",
    "county": "Fulton",
    "state": "IN",
    "auctionDate": "2026-03-17T10:00:00",
    "auctionDetail": {
      "date": "03/17/2026",
      "time": "10:00 AM",
      "location": "zeusauction.com",
      "type": "Online",
      "registration_start_date": "",
      "registration_end_date": ""
    }
  }
]
```

### Reference endpoints (not used by collector)

- `GET /api/property/states` — list of states with ids
- `GET /api/property/counties` — counties with state joinId
- `GET /api/property/saletypes` — sale type codes and names

## Data Flow

1. **Fetch**: `httpx.AsyncClient.post()` to `/api/auction/listall` with `startDate: today`, `recordCount: 500`
2. **Filter**: Keep only sale type codes A, C, D, J (drop F, R, B, O)
3. **Deduplicate**: Group by `(state, county, auctionDate date-only, sale_type)` — matches the project's canonical 4-field `DeduplicationKey`
4. **Normalize**: Map each record to an `Auction` Pydantic model

## Field Mapping

| API Field | Auction Field | Transformation |
|-----------|--------------|----------------|
| `state` | `state` | Direct (already 2-letter code) |
| `county` | `county` | Direct (already clean names like "LaPorte", "Fulton") |
| `auctionDate` | `start_date` | Parse ISO datetime, extract date |
| `saleTypeCode` | `sale_type` | A/D/J → `DEED`, C → `LIEN` |
| (constant) | `source_type` | `SourceType.VENDOR` |
| (constant) | `vendor` | `Vendor.SRI` |
| (constant) | `source_url` | `https://sriservices.com/properties` |
| (constant) | `confidence_score` | `1.0` (direct API data) |
| (not available) | `end_date` | `None` |
| (default) | `status` | `AuctionStatus.UPCOMING` (SRI only returns active/upcoming listings) |

## Sale Type Mapping

SRI uses its own sale type codes. We filter to tax-sale-relevant types and map:

| Code | SRI Name | Our SaleType | Rationale |
|------|----------|-------------|-----------|
| A | Tax Sale | `DEED` | General tax sales in IN/TN/LA transfer title |
| C | Certificate Sale | `LIEN` | Certificate sales are lien-based |
| D | Deed Sale | `DEED` | Direct deed transfer |
| J | Adjudicated Sale | `DEED` | LA adjudicated properties transfer title |

Excluded: F (Foreclosure), R (Redemption), B (Blighted), O (Tax Lien Sale — per user decision).

**Note**: `Vendor.SRI` already exists in `enums.py` — no enum changes needed.

## File Changes

### New files

- `src/tdc_auction_calendar/collectors/vendors/sri.py` — `SRICollector(BaseCollector)`
- `tests/collectors/vendors/test_sri.py` — unit tests with mocked httpx responses

### Modified files

- `src/tdc_auction_calendar/collectors/orchestrator.py` — add `"sri": SRICollector` to `COLLECTORS`
- `src/tdc_auction_calendar/collectors/vendors/__init__.py` — export `SRICollector`
- `src/tdc_auction_calendar/collectors/__init__.py` — re-export `SRICollector`

## Edge Cases

- **Volume / pagination**: Current data is ~150 records total (29 after type filtering). The API does not use cursor-based pagination; `recordCount: 500` is set high enough. No pagination loop needed.
- **Empty response**: API returns `[]` when no auctions match — handle gracefully, return empty list.
- **API key rotation**: Key is stored as a module-level `_API_KEY` constant for easy rotation. Embedded in the public JS bundle so not secret. Raise `ScrapeError` on 401/403 with a descriptive message mentioning the API key may need updating.
- **Request body rejection**: Raise `ScrapeError` on 400 Bad Request — may indicate the API contract has changed.
- **County name matching**: SRI county names (e.g. "LaPorte", "Bossier City") may not exactly match our seed data. We store as-is and let downstream matching handle normalization.
- **Duplicate dates**: Same county can have multiple auctions on the same date with different sale types — dedup key includes sale_type to preserve these as separate records: `(state, county, start_date, sale_type)`.
- **API unavailability**: Raise `ScrapeError` on HTTP errors or timeout (match Linebarger pattern).

## Testing Strategy

- Mock httpx responses with realistic JSON fixtures
- Test sale type filtering (only A, C, D, J kept)
- Test sale type mapping (A/D/J → DEED, C → LIEN)
- Test deduplication by (state, county, date, sale_type)
- Test empty response handling
- Test HTTP error / timeout handling wrapped in ScrapeError
- Test normalize() with complete and partial raw dicts
- Verify collector registration in orchestrator
