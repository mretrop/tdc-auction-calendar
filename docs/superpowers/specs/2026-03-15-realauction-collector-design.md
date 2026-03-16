# RealAuction Collector Design

**Date:** 2026-03-15
**Issue:** #50 — [M5] Collector: RealAuction county subdomains
**Status:** Draft

## Summary

Build a collector that scrapes RealAuction county auction portals for upcoming tax deed sale dates. The collector targets `.realtaxdeed.com` and `.realforeclose.com` subdomains across ~48 counties in FL, AZ, CO, and NJ, parsing their public auction calendar pages with CSS selectors.

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

The collector uses a hardcoded registry in `vendor_mapping.json`. Each entry includes state, county name, and base URL (subdomain). The full list:

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

### Florida — Combined Portals (7 counties)
These use `.realforeclose.com` and show both Foreclosure and Tax Deed; collector filters for TD only.

| County | Subdomain |
|--------|-----------|
| Calhoun | `calhoun.realforeclose.com` |
| Charlotte | `charlotte.realforeclose.com` |
| Manatee | `manatee.realforeclose.com` |
| Miami-Dade | `miamidade.realforeclose.com` |
| Okeechobee | `okeechobee.realforeclose.com` |
| St. Lucie | `stlucie.realforeclose.com` |
| Walton | `walton.realforeclose.com` |

### New Jersey (2 municipalities)
| Municipality | Subdomain |
|--------|-----------|
| Hardyston | `hardystonnj.realforeclose.com` |
| Newark | `newarknj.realforeclose.com` |

**Total: ~57 sites** (some may be foreclosure-only on combined portals; collector gracefully handles empty calendars).

## Collector Design

### Class: `RealAuctionCollector`

**File:** `src/tdc_auction_calendar/collectors/vendors/realauction.py`

Extends `BaseCollector`. Pattern follows MVBA/Arkansas (deterministic parsing, no LLM).

```
name = "realauction"
source_type = SourceType.VENDOR
```

### `_fetch()` Flow

1. Load RealAuction entries from `vendor_mapping.json` (filtered by `vendor == "RealAuction"`)
2. Create `ScrapeClient` via `create_scrape_client(stealth=StealthLevel.STEALTH)`
3. For each county entry:
   a. Build calendar URLs for current month + next 2 months
   b. Fetch each URL via `ScrapeClient` (gets raw HTML/markdown)
   c. Parse HTML with BeautifulSoup (already a project dependency via crawl4ai)
   d. Extract auction cells (`.CALSELT` selector)
   e. Filter for Tax Deed / Treasurer Deed entries
   f. Call `normalize()` on each extracted record
4. Return all auctions

### Month URL Generation

```python
def _calendar_url(self, base_url: str, year: int, month: int) -> str:
    date_param = f"{{ts '{year:04d}-{month:02d}-01 00:00:00'}}"
    return f"https://{base_url}/index.cfm?zaction=user&zmethod=calendar&selCalDate={date_param}"
```

For the current month, use no `selCalDate` param (defaults to current month).

### `normalize()` Mapping

| Source | Auction Field | Notes |
|--------|--------------|-------|
| `aria-label` | `start_date` | Parse `"March-05-2026"` format |
| `.CALTEXT` first text | `sale_type` | `SaleType.DEED` for both "Tax Deed" and "Treasurer Deed" |
| `.CALSCH` | `property_count` | Scheduled count (int) |
| `.CALTIME` | `notes` | e.g., `"10:00 AM ET"` |
| Registry entry | `state`, `county` | From vendor_mapping.json |
| Calendar page URL | `source_url` | The fetched calendar URL |
| Constant | `vendor` | `Vendor.RealAuction` |
| Constant | `source_type` | `SourceType.VENDOR` |
| Constant | `status` | `AuctionStatus.UPCOMING` |
| Constant | `confidence_score` | `0.90` |

### Rate Limiting

~150 requests total (57 counties x ~3 months). All subdomains resolve to the same RealAuction server infrastructure. The `ScrapeClient` rate limiter keys on domain, but since each subdomain is different, requests won't be naturally throttled against each other.

**Solution:** Use `asyncio.Semaphore` within the collector to limit concurrency (e.g., max 5 concurrent requests). Combined with the per-domain 2s rate limit on retries, this prevents hammering RealAuction's shared infrastructure.

### Error Handling

- **403 on a county:** Log warning, skip county, continue with others
- **Empty calendar (no `.CALSELT` cells):** Normal — county has no auctions that month, skip silently
- **Malformed HTML:** Log warning with county name, skip that page
- **Network timeout:** `ScrapeClient` retry logic handles this (3 retries with exponential backoff)

## Vendor Mapping Updates

Add new entries to `vendor_mapping.json` for all ~57 sites. Each entry follows the existing format:

```json
{
  "vendor": "RealAuction",
  "state": "FL",
  "county": "Hillsborough",
  "portal_url": "https://hillsborough.realtaxdeed.com",
  "sale_type": "DEED"
}
```

The existing 20 FL RealAuction entries in `vendor_mapping.json` use `realforeclose.com` URLs — these will be updated to point to the correct `.realtaxdeed.com` subdomains where applicable, and new entries added for the ~37 additional counties.

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

### Integration Considerations

- The collector integrates into the existing CLI `collect` command via the orchestrator
- Dedup key `(state, county, start_date, sale_type)` naturally handles overlap between this collector and others (e.g., CountyWebsiteCollector, StatutoryCollector)

## Dependencies

No new dependencies required:
- `beautifulsoup4` — already available via crawl4ai dependency
- `ScrapeClient` — existing infrastructure
- `BaseCollector` — existing base class

## Open Questions

None — all design decisions resolved during brainstorming.
