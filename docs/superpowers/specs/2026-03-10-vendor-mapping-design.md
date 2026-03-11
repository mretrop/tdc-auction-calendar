# Vendor Mapping Seed Data Design

**Issue**: #6 — [M1] Seed data: vendor_mapping.json
**Date**: 2026-03-10
**Status**: Approved

## Purpose

Create `vendor_mapping.json` — a reference mapping of known auction vendors to jurisdictions, with portal URLs. Used by the statutory collector to enrich auction records with vendor info and portal links.

## Relationship to Existing Data

`CountyInfoRow.known_auction_vendor` answers "who runs this county's auction?" (simple tag). `vendor_mapping.json` answers "what do we know about each vendor's relationship to jurisdictions?" (richer metadata with URLs). They coexist — vendor_mapping is the reference table, known_auction_vendor is the denormalized convenience field.

## JSON Schema

File: `src/tdc_auction_calendar/db/seed/vendor_mapping.json`

```json
[
  {
    "vendor": "RealAuction",
    "vendor_url": "https://www.realauction.com",
    "state": "FL",
    "county": "Miami-Dade",
    "portal_url": "https://miamidade.realforeclose.com"
  }
]
```

- **Primary key**: composite `(vendor, state, county)`
- **`county`**: county name matching counties.json, or `"all"` for statewide contracts
- **`vendor`** allowed values: `RealAuction`, `Bid4Assets`, `GovEase`, `Grant Street`, `SRI`
- All URLs must be valid HTTP/HTTPS format

## Models

### Pydantic: `VendorMapping`

| Field | Type | Constraints |
|-------|------|-------------|
| vendor | str | One of allowed vendor names |
| vendor_url | str | Valid HTTP(S) URL |
| state | str | 2-letter state code |
| county | str | County name or "all" |
| portal_url | str | Valid HTTP(S) URL |

### ORM: `VendorMappingRow`

- Table: `vendor_mapping`
- Composite PK: `(vendor, state, county)`
- All columns: `String`, non-nullable

## Seed Loader Update

Add to `_SEED_MAP` in `seed_loader.py`:

```python
"vendor_mapping": (VendorMappingRow, ["vendor", "state", "county"]),
```

## Alembic Migration

New migration to create the `vendor_mapping` table with columns matching ORM model.

## Data Coverage

Target ~55-65 entries across all 5 vendors:

| Vendor | Focus | Est. Entries |
|--------|-------|-------------|
| RealAuction | FL counties sample + other states | ~20-25 |
| Bid4Assets | DC, NJ, PA, select others | ~10-12 |
| GovEase | Midwest/South (IN, AL, etc.) | ~8-10 |
| Grant Street | PA, NJ, various | ~8-10 |
| SRI | TX counties | ~8-10 |

## Tests

File: `tests/test_seed_vendor_mapping.py`

1. Seed file exists and loads
2. At least 50 entries
3. All entries validate against `VendorMapping` Pydantic model
4. All entries instantiate as `VendorMappingRow` ORM model
5. No duplicate `(vendor, state, county)` keys
6. All vendor names in allowed set
7. All state codes exist in states.json (referential integrity)
8. All URLs are valid format
9. All non-"all" county values exist in counties.json for that state
10. Spot-check known mappings
11. Cross-validation: every `known_auction_vendor` in counties.json has corresponding vendor_mapping entry

## Acceptance Criteria (from issue)

- [ ] At least 50 vendor-to-jurisdiction mappings
- [ ] All vendor_url and portal_url values are valid URLs
- [ ] Used by statutory collector to enrich records with vendor info
