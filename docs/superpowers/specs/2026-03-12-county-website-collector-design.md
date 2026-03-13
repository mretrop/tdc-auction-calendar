# County Website Collector Design

**Issue:** #13 — [M2] County website collector
**Date:** 2026-03-12

## Overview

A single collector that iterates counties with `tax_sale_page_url` populated in the seed data, scrapes each county's tax sale page, and extracts auction dates using a generic LLM extraction schema. Returns all successfully extracted auctions; logs and skips failures.

## Decisions

- **Single generic extraction schema** for all counties (no per-county configs). The LLM handles HTML variance.
- **Failure handling:** Log warning and skip failed counties. No fallback to statutory data — the statutory collector runs separately.
- **URL population:** Populate ~50+ real `tax_sale_page_url` values in `counties.json` for states with existing collectors (FL, PA, NC, SC, MN, UT, NJ, CO, CA, AR, IA).
- **Serial iteration** with per-domain rate limiting. Concurrency deferred to orchestrator (issue #15).

## Files

### New

| File | Purpose |
|------|---------|
| `src/tdc_auction_calendar/collectors/county_websites/__init__.py` | Package init, export `CountyWebsiteCollector` |
| `src/tdc_auction_calendar/collectors/county_websites/county_collector.py` | Main collector class |
| `tests/collectors/county_websites/__init__.py` | Test package |
| `tests/collectors/county_websites/test_county_collector.py` | Tests |
| `tests/fixtures/county_websites/*.json` | Fixture data simulating extraction results |

### Modified

| File | Change |
|------|--------|
| `src/tdc_auction_calendar/db/seed/counties.json` | Populate `tax_sale_page_url` for ~50+ counties |
| `src/tdc_auction_calendar/collectors/__init__.py` | Export `CountyWebsiteCollector` |

## Extraction Schema

```python
class CountyAuctionRecord(BaseModel):
    """Schema for extraction from a single county's tax sale page."""
    sale_date: str              # ISO YYYY-MM-DD
    sale_type: str = ""         # lien/deed/hybrid; empty falls back to county's known type
    end_date: str | None = None
    deposit_amount: str | None = None
    registration_deadline: str | None = None
```

County and state are NOT extracted — they come from the seed data since we already know which county page we're scraping.

## Collector Design

```python
class CountyWebsiteCollector(BaseCollector):
    """Scrapes individual county tax sale pages for auction dates."""

    confidence_score: float = 0.70
    source_type = SourceType.COUNTY_WEBSITE

    _EXTRACTION_PROMPT = (
        "Extract tax sale / tax lien sale / tax deed sale auction information "
        "from this county page. For each upcoming sale, extract: sale date "
        "(ISO YYYY-MM-DD), sale type (lien, deed, or hybrid), end date if "
        "listed, deposit amount, and registration deadline."
    )
```

### Init

- Load counties from seed data (read `counties.json` directly via `SEED_DIR`)
- Filter to counties where `tax_sale_page_url` is not null
- Store as list of dicts with `state_code`, `county_name`, `tax_sale_page_url`, `sale_type` (for fallback)

### _fetch() loop

```
for each county with tax_sale_page_url:
    try:
        result = client.scrape(url, schema=CountyAuctionRecord)
        normalize result.data → Auction objects
        - state/county from seed data
        - sale_type from extraction, or fall back to county's known sale_type
        - filter out past dates
        append to all_auctions
    except Exception:
        log warning (county, state, url)
        continue

return all_auctions
```

Key differences from other collectors:
- **No "all failed" raise** — partial results are fine since each county is independent
- **State/county come from seed data**, not extraction
- **Sale type fallback** uses the county's known `sale_type` from seed data (via state's `default_sale_type`)

### normalize()

```python
def _normalize_record(self, raw: dict, county_info: dict) -> Auction:
    return Auction(
        state=county_info["state_code"],
        county=county_info["county_name"],
        start_date=date.fromisoformat(raw["sale_date"]),
        sale_type=SaleType(raw.get("sale_type") or county_info["default_sale_type"]),
        source_type=SourceType.COUNTY_WEBSITE,
        source_url=county_info["tax_sale_page_url"],
        confidence_score=self.confidence_score,
        end_date=date.fromisoformat(raw["end_date"]) if raw.get("end_date") else None,
        deposit_amount=Decimal(raw["deposit_amount"]) if raw.get("deposit_amount") else None,
        registration_deadline=(
            date.fromisoformat(raw["registration_deadline"])
            if raw.get("registration_deadline") else None
        ),
    )
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| County scrape fails (network, timeout, etc.) | Log warning with county/state/URL, skip to next |
| Extraction returns unexpected type | Log warning, skip county |
| Individual record fails normalization | Log error, skip record, continue |
| All records for one county fail normalization | Log error, continue to next county |
| No counties have URLs populated | Return empty list |
| Past dates in extraction | Filter out silently |

## Seed Data Population

Populate `tax_sale_page_url` for ~50+ counties across these states:
- FL, PA, NC, SC, MN, UT, NJ (public notice collector states)
- CO, CA, AR, IA (state agency collector states)

Focus on counties already in `counties.json` that have active tax sales. URLs should point to the county's treasurer/tax collector page that lists upcoming tax sale dates.

## Testing

### Test cases

| Test | Description |
|------|-------------|
| `test_name` | Returns "county_website" |
| `test_source_type` | Returns COUNTY_WEBSITE |
| `test_loads_counties_with_urls` | Only counties with populated URLs are loaded |
| `test_fetch_returns_auctions` | Fixture data produces auctions |
| `test_fetch_skips_failed_counties` | Failed scrapes don't crash, other counties still work |
| `test_fetch_skips_invalid_records` | Bad records within a county are skipped |
| `test_fetch_filters_past_dates` | Past dates are excluded |
| `test_fetch_empty_urls_returns_empty` | No populated URLs → empty list |
| `test_normalize_uses_seed_county_info` | State/county come from seed, not extraction |
| `test_normalize_falls_back_sale_type` | Empty/missing sale_type uses county's default |
| `test_normalize_optional_fields` | end_date, deposit_amount, registration_deadline handled |
| `test_closes_client_on_failure` | client.close() called even on exception |
| `test_acceptance_50_counties` | Fixture produces >= 50 county records |

### Fixtures

JSON files simulating extraction results for counties across multiple states. Each fixture contains records that would come back from a county page extraction. One fixture per state with multiple counties.

## Confidence Score

0.70 — lowest of the three collector types:
- State agency: 0.85 (authoritative, structured)
- Public notice: 0.75 (semi-structured, keyword search)
- County website: 0.70 (most varied, per-county pages, highest extraction risk)
