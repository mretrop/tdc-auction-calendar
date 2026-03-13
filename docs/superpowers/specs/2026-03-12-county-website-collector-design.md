# County Website Collector Design

**Issue:** #13 — [M2] County website collector
**Date:** 2026-03-12

## Overview

A single collector that iterates counties with `tax_sale_page_url` populated in the seed data, scrapes each county's tax sale page, and extracts auction dates using a generic LLM extraction schema. Returns all successfully extracted auctions; logs and skips failures.

## Decisions

- **Single generic extraction schema** for all counties (no per-county configs). The LLM handles HTML variance.
- **Failure handling:** Log warning and skip failed counties. The statutory collector runs separately and naturally fills gaps — no explicit fallback logic needed in this collector. The orchestrator (issue #15) handles source merging/prioritization. This satisfies the issue's "graceful fallback" criterion: the system as a whole falls back to statutory data, but each collector has a single responsibility.
- **URL population:** Populate ~50+ real `tax_sale_page_url` values in `counties.json` for states with existing collectors (FL, PA, NC, SC, MN, UT, NJ, CO, CA, AR, IA).
- **Serial iteration** with per-domain rate limiting (handled automatically by `ScrapeClient`'s built-in `RateLimiter`). Concurrency deferred to orchestrator (issue #15).
- **LLM schema extraction** (not `json_options`): County pages have the most HTML variance, so `schema=CountyAuctionRecord` with Claude API extraction is the right choice over Cloudflare's server-side `json_options`.

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
    sale_type: str = ""         # lien/deed/hybrid; empty falls back to state's default
    end_date: str | None = None
    deposit_amount: str | None = None  # numeric string, no currency symbols
    registration_deadline: str | None = None
```

County and state are NOT extracted — they come from the seed data since we already know which county page we're scraping.

The extraction prompt instructs the LLM to return `deposit_amount` as a plain numeric string (no `$` or commas) to simplify Decimal conversion.

## Collector Design

```python
class CountyWebsiteCollector(BaseCollector):
    """Scrapes individual county tax sale pages for auction dates."""

    confidence_score: float = 0.70

    _EXTRACTION_PROMPT = (
        "Extract tax sale / tax lien sale / tax deed sale auction information "
        "from this county page. For each upcoming sale, extract: sale date "
        "(ISO YYYY-MM-DD), sale type (lien, deed, or hybrid), end date if "
        "listed, deposit amount (numeric only, no $ or commas), and "
        "registration deadline (ISO YYYY-MM-DD)."
    )

    @property
    def name(self) -> str:
        return "county_website"

    @property
    def source_type(self) -> SourceType:
        return SourceType.COUNTY_WEBSITE
```

### Init

- Load both `counties.json` and `states.json` from `SEED_DIR`
- Join on `state_code` to get each county's default `sale_type` from its state record
- Filter to counties where `tax_sale_page_url` is not null
- Store as list of `_CountyTarget` dicts: `state_code`, `county_name`, `tax_sale_page_url`, `default_sale_type`

### _fetch() loop

```
client = create_scrape_client()
try:
    for each county_target:
        try:
            result = client.scrape(url, schema=CountyAuctionRecord)
            validate result.data type (list/dict/None)
            normalize each record → Auction
            - state/county from county_target
            - sale_type from extraction, or fall back to county_target.default_sale_type
            - filter out past dates
            append to all_auctions
        except Exception:
            log warning (county, state, url)
            continue
finally:
    client.close()

return all_auctions
```

Key differences from other collectors:
- **No "all failed" raise** — partial results are fine since each county is independent
- **State/county come from seed data**, not extraction
- **Sale type fallback** uses the state's default `sale_type` from seed data
- **One ScrapeClient** shared across all county scrapes (created once, closed in finally)

### normalize()

The `BaseCollector` ABC requires `normalize(self, raw: dict) -> Auction`. Since this collector needs county context during normalization, the approach is:

- `normalize()` is not used directly — `_fetch()` calls `_normalize_record()` with county context
- `normalize()` is implemented to satisfy the ABC but raises `NotImplementedError` (it should never be called without county context)

```python
def normalize(self, raw: dict) -> Auction:
    raise NotImplementedError("Use _normalize_record() with county_target context")

def _normalize_record(self, raw: dict, county_target: dict) -> Auction:
    return Auction(
        state=county_target["state_code"],
        county=county_target["county_name"],
        start_date=date.fromisoformat(raw["sale_date"]),
        sale_type=SaleType(raw.get("sale_type") or county_target["default_sale_type"]),
        source_type=SourceType.COUNTY_WEBSITE,
        source_url=county_target["tax_sale_page_url"],
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
| `test_normalize_falls_back_sale_type` | Empty/missing sale_type uses state's default |
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
