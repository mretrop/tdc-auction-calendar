# PublicSurplus Collector Design

## Summary

Add a collector for PublicSurplus (publicsurplus.com) Tax Sale and Lien auctions. The collector scrapes category listing pages to discover auctions, then fetches individual detail pages to extract actual start/end dates for the calendar.

## Decisions

- **Fetcher**: Plain `httpx.AsyncClient` (no ScrapeClient) — server-rendered HTML, no bot protection observed
- **Extraction**: BeautifulSoup CSS selectors (deterministic, no LLM)
- **County**: Parse from title when possible, default to "Various"
- **Dates**: Two-pass approach — list pages for discovery + end date from JS, detail pages for start date. End date from JS serves as fallback if detail page fails.
- **Concurrency**: `asyncio.Semaphore(3)` for detail page fetches
- **Scope**: Start with unfiltered Tax Sale/Lien categories (all states), paginate. Switch to per-state URLs if pagination becomes unwieldy.
- **US-only**: Skip non-US state codes (Canadian provinces appear on the site but are out of scope)

## Architecture

Single file: `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`

Subclasses `BaseCollector`. Follows the Bid4Assets pattern (httpx + BeautifulSoup, bypasses ScrapeClient).

### Two-Pass Fetch

**Pass 1 — List pages**: Fetch category pages for Tax Sale (`catid=1506`) and Lien (`catid=1505`). Paginate through all results. Extract per-auction: ID, state, title, source URL, end date (from embedded JS), and which category it came from.

**Pass 2 — Detail pages**: For each discovered auction, fetch `/sms/auction/view?auc={id}` to extract start date (and end date if available). Capped at 3 concurrent requests via semaphore.

### List Page Parsing

Target HTML structure:
```html
<div class="auction-item" id="{auction_id}catGrid">
  <div class="auction-item-img">
    <a href="/sms/auction/view?auc={auction_id}">...</a>
    <span class="auction-item-state">MN</span>
  </div>
  <div class="auction-item-body px-0">
    <h6 class="w-100 card-title ps-card-feat__body--title ps-1 mb-2">
      <a href="..." title="#3946030 - 2025 Forfeiture Minimum Bid Sale: 25-5311-25765">
        #3946030 - 2025 Forfeiture Minimum Bid S...
      </a>
    </h6>
    ...
    <script>
      updateTimeLeftSpan(timeLeftInfoMap, 3946030, "3946030catGrid",
        1773711883006, 1773846000000, 0, "", "", "catList", timeLeftCallback);
    </script>
  </div>
</div>
```

Selectors:
- Auction items: `div.auction-item`
- Auction ID: `div.auction-item` `id` attribute, strip `catGrid` suffix
- State: `span.auction-item-state` text, stripped
- Title: `h6.card-title a` `title` attribute (full, untruncated)
- Source URL: constructed as `https://www.publicsurplus.com/sms/auction/view?auc={id}`
- End date: extracted from `updateTimeLeftSpan()` JS call — 5th argument is auction end time as epoch milliseconds

JS timestamp extraction regex: `r'updateTimeLeftSpan\([^,]+,\s*(\d+),\s*"[^"]+",\s*\d+,\s*(\d+)'` — capture group 1 = auction ID, group 2 = end epoch ms.

Note: the 4th argument (skipped by `\d+`) is the **server render time**, not a per-auction start time. This was verified by confirming all auctions on a page share the same 4th argument value while having different 5th arguments (end times). The difference between the 4th and 5th arguments matches the displayed "Time Left" values. Start dates are only available from detail pages.

### Pagination

Pagination is URL-parameter-based, not link-based. The list page uses a `page` query parameter (0-indexed):
```
GET /sms/browse/cataucs?catid=1506&page=0
GET /sms/browse/cataucs?catid=1506&page=1
...
```

Increment `page` until zero auction items are returned. Safety cap at 20 pages to prevent runaway scraping. Add a 0.5s delay between page fetches to be polite.

### Detail Page Parsing

**Discovery task**: No research sample of a detail page exists yet. During implementation, the first step is to fetch a sample detail page and save it as a test fixture. Expected: the detail page will contain start/end dates in a structured format (likely a labeled field like "Opens:" / "Closes:" or similar).

The detail page parser will be designed after examining the actual HTML. If the detail page does not yield a usable start date, fall back to using the end date from the list page JS as `start_date` (for online auctions, the close date is the most actionable date for the calendar).

### County Extraction

Attempt to parse county name from the auction title using regex. Known patterns:
- "Norman County Tax-Forfeiture Parcel..." → "Norman"
- "Mohave County Land Sale..." → "Mohave"
- "Parcel 2 PIN#26-345-0510" → no match → "Various"

Pattern: `r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+County\b'` — match one or more capitalized words before "County" (e.g., "Norman County", "St. Louis County"). More targeted than a generic `\w+` to avoid false matches on surrounding text.

If no match, set county to "Various".

### US State Filtering

Validate the 2-letter state code from `.auction-item-state` against a set of valid US state abbreviations. Skip any auction with a non-US code (Canadian provinces like AB, BC, ON appear on PublicSurplus). The set is defined as a module-level constant `US_STATES`.

### List Page Fetching

List pages are fetched **sequentially** (one page at a time) with a 0.5s delay between requests. Only detail page fetches are concurrent (semaphore of 3).

### Deduplication Behavior

Multiple parcels from the same county auction (e.g., seven Norman County Tax-Forfeiture tracts) will share the same dedup key `(state, county, start_date, sale_type)` and collapse into one calendar entry. This is correct — the calendar shows auction events, not individual parcels. The detail page fetch for duplicate parcels is wasted work but acceptable given the small volume.

### Normalization

Map to `Auction` model:
- `state`: from list page `.auction-item-state` (skip non-US 2-letter codes)
- `county`: from title regex or "Various"
- `start_date`: from detail page, or end date from JS as fallback
- `end_date`: from detail page or JS epoch timestamp
- `sale_type`: `SaleType.DEED` for catid=1506 (Tax Sale), `SaleType.LIEN` for catid=1505. Note: titles include terms like "Forfeiture Minimum Bid Sale" and "Tax-Forfeiture" which are state-specific variants — mapping to DEED is an acceptable simplification for v1.
- `vendor`: `Vendor.PUBLIC_SURPLUS` (new enum value)
- `source_type`: `SourceType.VENDOR`
- `source_url`: detail page URL
- `confidence_score`: 0.80 (county may be approximate via "Various" fallback, and detail page date parsing is a discovery task)
- `notes`: auction title (for context, since county may be "Various")

### Enum Addition

Add `PUBLIC_SURPLUS = "PublicSurplus"` to the `Vendor` enum in `models/enums.py`.

## Error Handling

- **Empty categories**: Log info, continue (not an error)
- **Detail page fetch failures**: Log warning, use end date from JS as fallback for `start_date`. If no JS end date either, skip the auction.
- **Unparseable dates**: Skip the auction (no date = useless for calendar)
- **County regex misses**: Default to "Various"
- **HTTP 429 / 5xx**: Log and skip. No retry logic in v1.
- **Non-US states**: Skip silently (Canadian provinces, territories)
- **Non-tax items**: Category filtering (catid=1506/1505) prevents most. Any that leak through come with "Various" county — harmless.

## Risks & Assumptions

- **Research data is from catid=15 (parent Real Estate category)**, not catid=1506/1505 directly. The HTML structure is expected to be identical since the same template renders all sub-categories, but implementation should verify this.
- **Detail page structure is unknown** and will be discovered during implementation. The JS end-date fallback ensures the collector can still produce usable data even if detail page parsing proves difficult.

## Testing

- Unit tests for `parse_listing_html()` with saved HTML fixtures
- Unit tests for `parse_detail_html()` with saved HTML fixtures (created during implementation after fetching a sample)
- Unit tests for JS timestamp extraction
- Unit tests for county extraction regex against known title patterns
- Unit test for `normalize()` mapping raw dicts to `Auction`
- Integration test against live site (marked `pytest.mark.integration`)

## References

- Issue: #57
- Research HTML: `data/research/sub/publicsurplus_recrawl.html` (catid=15, parent category)
- Research markdown: `data/research/sub/publicsurplus_recrawl.md`
- Crawl research: #52
