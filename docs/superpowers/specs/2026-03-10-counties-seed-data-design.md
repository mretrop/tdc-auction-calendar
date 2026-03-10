# Counties Seed Data Design (Issue #5)

## Overview

Create `counties.json` seed data with 200+ county records for the TDC Auction Calendar. Covers all counties in FL, IL, NJ, CO, CA plus top metro counties from remaining states.

## Data File

**Path:** `src/tdc_auction_calendar/db/seed/counties.json`

Array of objects matching the `CountyInfo` Pydantic model:

```json
{
  "fips_code": "12086",
  "state": "FL",
  "county_name": "Miami-Dade",
  "treasurer_url": null,
  "tax_sale_page_url": null,
  "known_auction_vendor": "RealAuction",
  "timezone": "America/New_York",
  "priority": "high"
}
```

### Coverage Strategy

- **Full coverage states (all counties):** FL (67), IL (102), NJ (21), CO (64), CA (58) — ~312 counties
- **Top metros from remaining states:** ~50 additional high-population counties
- Total comfortably exceeds 200

### Data Sourcing (Option C — Hybrid)

- FIPS codes, state, county name, timezone: generated from training knowledge (stable facts)
- `known_auction_vendor`: populated for well-known mappings (e.g., FL uses RealAuction), null where uncertain
- `treasurer_url`, `tax_sale_page_url`: null (to be filled via scraping/research later)

### Priority Assignment

- `high`: Top 100 metro counties by population + all FL counties
- `medium`: Remaining counties in full-coverage states
- `low`: Smaller counties included for completeness

## Test File

**Path:** `tests/test_seed_counties.py`

Mirrors `test_seed_states.py` pattern:

1. Seed file exists
2. Entry count >= 200
3. All entries validate against Pydantic `CountyInfo`
4. All entries instantiable as `CountyInfoRow` (ORM compatibility)
5. No duplicate FIPS codes
6. FIPS codes are valid — exactly 5 digits, all numeric
7. FIPS state prefix matches state field
8. All states referenced exist in `states.json` (referential integrity)
9. Valid priority values (Priority enum)
10. Valid timezone strings (IANA via zoneinfo)
11. Full coverage state minimums — FL >= 67, IL >= 102, NJ >= 21, CO >= 64, CA >= 58
12. Spot-check known counties (Miami-Dade, Cook, Los Angeles, etc.)

## Architecture Impact

None. Purely additive — two new files. `seed_loader.py` already maps `"counties"` to `CountyInfoRow`. No migrations or CLI changes needed.
