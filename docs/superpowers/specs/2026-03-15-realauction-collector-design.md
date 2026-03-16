# RealAuction Collector Design

**Date:** 2026-03-15
**Issue:** #50 — [M5] Collector: RealAuction county subdomains
**Status:** Approved

## Summary

Build a collector that scrapes RealAuction county auction portals for upcoming tax deed sale dates. The collector targets `.realtaxdeed.com` and `.realforeclose.com` subdomains across ~57 counties in FL, AZ, CO, and NJ, parsing their public auction calendar pages with CSS selectors on raw HTML.

## Background

RealAuction hosts online tax deed auctions for 200+ counties. The main directory at `realauction.com/clients` returns 403 (bot protection), but individual county subdomains are public bidder portals with lighter protection. Each portal has an identical ColdFusion-templated auction calendar page showing upcoming sale dates.

The client primarily cares about tax deed auctions (not foreclosure or tax lien).

## Site Discovery

The "Jump to" dropdown on any RealAuction county portal (`#JMP_MENU_SEL`) contains the full directory of all RealAuction sites with numeric vendor IDs. The AJAX endpoint `SwitchSite(vendorId)` resolves these IDs to subdomain URLs. We used this to build the complete registry.

## Subdomain Patterns

Three distinct URL patterns based on state/sale type:

| Pattern | States | Example |
|---------|--------|---------|
| `{county}.realtaxdeed.com` | FL, AZ | `hillsborough.realtaxdeed.com` |
| `{county}.treasurersdeedsale.realtaxdeed.com` | CO | `denver.treasurersdeedsale.realtaxdeed.com` |
| `{county}.realforeclose.com` | FL (combined), NJ | `miami-dade.realforeclose.com` |

Combined portals (`.realforeclose.com`) show both Foreclosure and Tax Deed entries on the same calendar. The collector filters for Tax Deed / Treasurer Deed entries only.

## Calendar Page Structure

**URL:** `{subdomain}/index.cfm?zaction=USER&zmethod=CALENDAR`

**Month navigation:** `?zaction=user&zmethod=calendar&selCalDate={ts '2026-04-01 00:00:00'}`

The calendar is server-rendered HTML. Auction dates use a consistent structure:

```html
<!-- Empty date cell -->
<div aria-label="March-04-2026" class="CALBOX CALW5">
  <span class="CALNUM">4</span>
</div>

<!-- Auction date cell -->
<div role="link" aria-label="March-05-2026"
     class="CALBOX CALW5 CALSELT" dayid="03/05/2026">
  <span class="CALNUM">5</span>
  <span class="CALTEXT">Tax Deed<br>
    <span class="CALMSG">
      <span class="CALACT">0</span> / <span class="CALSCH">13</span> TD<br>
    </span>
    <span class="CALTIME"> 10:00 AM ET</span>
  </span>
</div>
```

**Key selectors:**
- Auction cells: `.CALSELT` class (also have `role="link"`)
- Date: `aria-label` attribute (format: `"Month-DD-YYYY"`)
- Sale type: first text node of `.CALTEXT` (`"Tax Deed"`, `"Treasurer Deed"`, or `"Foreclosure"`)
- Scheduled property count: `.CALSCH` text content
- Active (sold) count: `.CALACT` text content
- Auction time: `.CALTIME` text content

**Filtering:** On combined portals, skip cells where `.CALTEXT` starts with `"Foreclosure"`. Accept `"Tax Deed"` and `"Treasurer Deed"`.

## Site Registry

The collector reads its site list from `vendor_mapping.json` via the database (`VendorMappingRow` table, filtered by `vendor == "RealAuction"`). Each entry's `portal_url` is the subdomain base URL; the collector appends the calendar path.

### Arizona (3 counties)
| County | Subdomain |
|--------|-----------|
| Apache | `apache.realtaxdeed.com` |
| Coconino | `coconino.realtaxdeed.com` |
| Mohave | `mohave.realtaxdeed.com` |

### Colorado (8 counties)
| County | Subdomain |
|--------|-----------|
| Adams | `adams.treasurersdeedsale.realtaxdeed.com` |
| Denver | `denver.treasurersdeedsale.realtaxdeed.com` |
| Eagle | `eagle.treasurersdeedsale.realtaxdeed.com` |
| El Paso | `elpasoco.treasurersdeedsale.realtaxdeed.com` |
| Larimer | `larimer.treasurersdeedsale.realtaxdeed.com` |
| Mesa | `mesa.treasurersdeedsale.realtaxdeed.com` |
| Pitkin | `pitkin.treasurersdeedsale.realtaxdeed.com` |
| Weld | `weld.treasurersdeedsale.realtaxdeed.com` |

### Florida — Dedicated Taxdeed Sites (37 counties)
| County | Subdomain |
|--------|-----------|
| Alachua | `alachua.realtaxdeed.com` |
| Baker | `baker.realtaxdeed.com` |
| Bay | `bay.realtaxdeed.com` |
| Brevard | `brevard.realtaxdeed.com` |
| Citrus | `citrus.realtaxdeed.com` |
| Clay | `clay.realtaxdeed.com` |
| Duval | `duval.realtaxdeed.com` |
| Escambia | `escambia.realtaxdeed.com` |
| Flagler | `flagler.realtaxdeed.com` |
| Gilchrist | `gilchrist.realtaxdeed.com` |
| Gulf | `gulf.realtaxdeed.com` |
| Hendry | `hendry.realtaxdeed.com` |
| Hernando | `hernando.realtaxdeed.com` |
| Highlands | `highlands.realtaxdeed.com` |
| Hillsborough | `hillsborough.realtaxdeed.com` |
| Indian River | `indianriver.realtaxdeed.com` |
| Jackson | `jackson.realtaxdeed.com` |
| Lake | `lake.realtaxdeed.com` |
| Lee | `lee.realtaxdeed.com` |
| Leon | `leon.realtaxdeed.com` |
| Marion | `marion.realtaxdeed.com` |
| Martin | `martin.realtaxdeed.com` |
| Monroe | `monroe.realtaxdeed.com` |
| Nassau | `nassau.realtaxdeed.com` |
| Orange | `orange.realtaxdeed.com` |
| Osceola | `osceola.realtaxdeed.com` |
| Palm Beach | `palmbeach.realtaxdeed.com` |
| Pasco | `pasco.realtaxdeed.com` |
| Pinellas | `pinellas.realtaxdeed.com` |
| Polk | `polk.realtaxdeed.com` |
| Putnam | `putnam.realtaxdeed.com` |
| Santa Rosa | `santarosa.realtaxdeed.com` |
| Sarasota | `sarasota.realtaxdeed.com` |
| Seminole | `seminole.realtaxdeed.com` |
| Suwannee | `suwannee.realtaxdeed.com` |
| Volusia | `volusia.realtaxdeed.com` |
| Washington | `washington.realtaxdeed.com` |

### Florida — Combined Portals (9 counties)
These use `.realforeclose.com` and show both Foreclosure and Tax Deed; collector filters for TD only.

| County | Subdomain | Notes |
|--------|-----------|-------|
| Broward | `broward.realforeclose.com` | Foreclosure-only in dropdown; may or may not have TD entries |
| Calhoun | `calhoun.realforeclose.com` | |
| Charlotte | `charlotte.realforeclose.com` | |
| Collier | `collier.realforeclose.com` | Not in dropdown; existing seed data entry — keep and test |
| Manatee | `manatee.realforeclose.com` | |
| Miami-Dade | `miamidade.realforeclose.com` | Confirmed: shows TD entries |
| Okeechobee | `okeechobee.realforeclose.com` | |
| St. Lucie | `stlucie.realforeclose.com` | |
| Walton | `walton.realforeclose.com` | |

### New Jersey (2 entries)
NJ entries are municipalities, not counties. Use the municipality name in the `county` field for consistency with the existing `VendorMappingRow` schema (which uses `county` as the field name). This is acceptable — the dedup key just needs a consistent identifier per jurisdiction.

| Municipality | Subdomain |
|--------|-----------|
| Hardyston | `hardystonnj.realforeclose.com` |
| Newark | `newarknj.realforeclose.com` |

**Total: ~59 sites** (some may be foreclosure-only on combined portals; collector gracefully handles empty calendars).

## Collector Design

### Class: `RealAuctionCollector`

**File:** `src/tdc_auction_calendar/collectors/vendors/realauction.py`

Extends `BaseCollector`. Pattern follows MVBA/Arkansas (deterministic parsing, no LLM).

```
name = "realauction"  # matches orchestrator key
source_type = SourceType.VENDOR
```

### `_fetch()` Flow

1. Query `VendorMappingRow` table filtered by `vendor == "RealAuction"` to get the site list
2. Create `ScrapeClient` via `create_scrape_client(stealth=StealthLevel.STEALTH)`
3. Use `asyncio.Semaphore(5)` to limit concurrent requests across all counties
4. Use `asyncio.gather()` to fetch all county/month combinations concurrently (bounded by semaphore):
   - For each county entry, build calendar URLs for current month + next 2 months
   - Fetch each URL via `ScrapeClient`
   - Parse raw HTML via `result.fetch.html` with BeautifulSoup
   - Extract auction cells (`.CALSELT` selector)
   - Filter for Tax Deed / Treasurer Deed entries
   - Call `normalize()` on each extracted record
5. Return all auctions

### HTML Access

Both `CloudflareFetcher` and `Crawl4AiFetcher` populate `FetchResult.html` with the raw page HTML. The collector uses `result.fetch.html` (not `result.fetch.markdown`) because CSS class selectors (`.CALSELT`, `.CALTEXT`, `.CALSCH`, `.CALTIME`) are stripped during markdown conversion.

### Month URL Generation

```python
def _calendar_url(self, base_url: str, year: int, month: int) -> str:
    date_param = f"{{ts '{year:04d}-{month:02d}-01 00:00:00'}}"
    return f"{base_url}/index.cfm?zaction=user&zmethod=calendar&selCalDate={date_param}"
```

For the current month, use no `selCalDate` param (defaults to current month).

### `normalize()` Mapping

| Source | Auction Field | Notes |
|--------|--------------|-------|
| `aria-label` | `start_date` | Parse `"March-05-2026"` format |
| `.CALTEXT` first text | `sale_type` | `SaleType.DEED` for both "Tax Deed" and "Treasurer Deed" |
| `.CALSCH` | `property_count` | Scheduled count (int) |
| `.CALTIME` | `notes` | e.g., `"10:00 AM ET"` |
| Registry entry | `state`, `county` | From VendorMappingRow |
| Calendar page URL | `source_url` | The fetched calendar URL |
| Constant | `vendor` | `Vendor.RealAuction` |
| Constant | `source_type` | `SourceType.VENDOR` |
| Constant | `status` | `AuctionStatus.UPCOMING` |
| Constant | `confidence_score` | `0.90` (deterministic parsing of structured HTML, but auctions can be cancelled between scrapes) |

### Rate Limiting

~175 requests total (59 counties x ~3 months). All subdomains resolve to the same RealAuction server infrastructure. The `ScrapeClient` rate limiter keys on domain, but since each subdomain is different, requests won't be naturally throttled against each other.

**Solution:** Use `asyncio.Semaphore(5)` within the collector to limit concurrency. Combined with the per-domain 2s rate limit on retries, this prevents hammering RealAuction's shared infrastructure.

### Error Handling

- **403 on a county:** Log warning, skip county, continue with others
- **Empty calendar (no `.CALSELT` cells):** Normal — county has no auctions that month, skip silently
- **Malformed HTML / `html` field is None:** Log warning with county name, skip that page
- **Network timeout:** `ScrapeClient` retry logic handles this (3 retries with exponential backoff)
- **Partial failures:** If N of 59 counties fail, collector returns results from the successful ones

## Vendor Mapping Updates

Update and expand `vendor_mapping.json` RealAuction entries. Each entry follows the existing schema:

```json
{
  "vendor": "RealAuction",
  "vendor_url": "https://www.realauction.com",
  "state": "FL",
  "county": "Hillsborough",
  "portal_url": "https://hillsborough.realtaxdeed.com"
}
```

### Migration Plan for Existing 20 Entries

The existing 20 FL entries all use `.realforeclose.com` URLs. Changes:

- **Update portal_url** for counties that have dedicated `.realtaxdeed.com` subdomains (e.g., Hillsborough, Orange, Duval, Pinellas, Lee, Polk, Brevard, Volusia, Seminole, Sarasota, Pasco, Escambia, Leon, Osceola, Marion, Palm Beach)
- **Keep `.realforeclose.com`** for combined portals (Miami-Dade, Broward, Manatee, Collier)
- **Add ~39 new entries** for AZ, CO, NJ, and additional FL counties not in the current seed

### Orchestrator Registration

The new collector must be registered in:
- `src/tdc_auction_calendar/collectors/vendors/__init__.py` (export)
- `src/tdc_auction_calendar/collectors/__init__.py` (re-export + `__all__`)
- `src/tdc_auction_calendar/collectors/orchestrator.py` (COLLECTORS dict)

## Testing

### Unit Tests

**File:** `tests/test_realauction_collector.py`

1. **HTML fixture parsing:** Save actual calendar HTML from Hillsborough (with auctions) and Apache (empty) as test fixtures
2. **`parse_calendar_page()`:** Verify correct extraction of date, sale type, property count, time from fixture HTML
3. **Filtering:** Verify Foreclosure entries are skipped on combined portal HTML (Miami-Dade fixture)
4. **`normalize()`:** Verify correct Auction model construction from parsed data
5. **Month URL generation:** Verify correct URL format for different months
6. **Sale type mapping:** "Tax Deed" -> DEED, "Treasurer Deed" -> DEED, "Foreclosure" -> skipped
7. **Date parsing:** Verify `"March-05-2026"` aria-label format parses correctly
8. **Partial failure:** Verify collector returns results from successful counties when some fail

### Integration Considerations

- The collector integrates into the existing CLI `collect` command via the orchestrator
- Dedup key `(state, county, start_date, sale_type)` naturally handles overlap between this collector and others (e.g., CountyWebsiteCollector, StatutoryCollector)

## Dependencies

- `beautifulsoup4` — add as direct dependency in `pyproject.toml` (currently only transitive via crawl4ai)
- `ScrapeClient` — existing infrastructure
- `BaseCollector` — existing base class
