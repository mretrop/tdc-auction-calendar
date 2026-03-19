# Precise Source Links Design

**Date:** 2026-03-18
**Goal:** Improve `source_url` precision across all collectors so end users get the most useful link possible for each auction event.

## Problem

Several collectors set `source_url` to generic landing pages rather than event-specific or county-specific URLs. When a user clicks a source link in their calendar (iCal, RSS, etc.), they land on a broad page and have to hunt for the specific auction.

## Current State

| Collector | Current Link | Specific? |
|-----------|-------------|-----------|
| PublicSurplus | Auction detail page | Yes |
| Purdue | County/precinct PDF | Yes |
| Bid4Assets | Storefront link (w/ fallback) | Mostly |
| RealAuction | County calendar page (month view) | No |
| MVBA | Monthly sales landing page | No |
| Linebarger | State-level map | No (keep as-is) |
| SRI | Generic /properties page | No |

## Changes

### 1. RealAuction — Auction Preview Deep Link

**File:** `src/tdc_auction_calendar/collectors/vendors/realauction.py`

In `_fetch_one`, replace `source_url: url` (the calendar page) with a constructed preview URL using `base_url` (already a parameter) and the parsed entry date:

```
{base_url}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={entry_date:%m/%d/%Y}
```

**Important:** The `SITES` tuple contains three distinct domain patterns (`*.realtaxdeed.com`, `*.realforeclose.com`, `*.treasurersdeedsale.realtaxdeed.com`) and subdomains don't always match county names (e.g., El Paso → `elpasoco`, Sussex NJ → `hardystonnj`). We must use the `base_url` from the tuple directly — not construct a URL from the county name.

The `AUCTIONDATE` parameter uses `MM/DD/YYYY` format with literal slashes (the user confirmed this pattern works: `AUCTIONDATE=03/03/2026`). The slashes will be preserved as-is in the URL since ColdFusion/IIS handles them.

### 2. MVBA — Per-County PDF/Auction Links

**File:** `src/tdc_auction_calendar/collectors/vendors/mvba.py`

The markdown contains per-county links (PDFs or auction detail pages), but `parse_monthly_sales()` discards them — the `_COUNTY_RE` regex stops at `]` and doesn't capture the `(url)` portion.

**Changes:**
1. Extend `_COUNTY_RE` to also capture the URL from the markdown link syntax `[text](url)`
2. Update `parse_monthly_sales()` to return `(date, county_name, url | None)` tuples
3. The collector passes the extracted URL as `source_url`, falling back to the generic monthly sales page URL if no link is present
4. Update existing tests that destructure two-element tuples to handle the new three-element return type

### 3. SRI Services — Auction List Deep Link

**File:** `src/tdc_auction_calendar/collectors/vendors/sri.py`

Construct a filtered URL that opens the auction list modal:

```
https://sriservices.com/properties?state={state}&saleType={sale_type_label}&county={county_encoded}&modal=auctionList
```

The user confirmed this URL pattern works (example: `?state=FL&saleType=redemption&county=St.+Johns&modal=auctionList`).

**`saleTypeCode` to URL `saleType` mapping:**

| API `saleTypeCode` | Our `SaleType` | URL `saleType` param |
|---------------------|----------------|----------------------|
| `A` | DEED | `tax` |
| `C` | LIEN | `redemption` |
| `D` | DEED | `deed` |
| `J` | DEED | `adjudicated` |

> Note: The exact URL label values need live verification during implementation. The SRI frontend may use different labels — check the site's filter UI to confirm.

County names must be URL-encoded (e.g., `St. Johns` → `St.+Johns`).

## Out of Scope

- **Linebarger** — state-level map URL is the best available; county-level requires lat/lon/bbox coordinates not in the API
- **Bid4Assets** — already extracts storefront deep links with generic fallback
- **PublicSurplus** — already links to specific auction detail pages
- **Purdue** — already links to county/precinct PDFs

## Deduplication Note

The dedup key is `(state, county, start_date, sale_type)` — `source_url` is not part of it. Existing records will get updated URLs on the next collection run with no dedup issues.

## Testing

Each collector change is isolated. Verify by:
1. Running existing collector unit tests (update MVBA tests for new return type)
2. Adding/updating test assertions to validate the new URL patterns
3. Spot-checking generated URLs against the live sites (especially SRI `saleType` labels)

## Impact

All four exporters (iCal, JSON, CSV, RSS) automatically benefit — they already read `source_url` from the Auction model, so no exporter changes are needed.
