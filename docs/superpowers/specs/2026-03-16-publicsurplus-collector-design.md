# PublicSurplus Collector Design

## Summary

Add a collector for PublicSurplus (publicsurplus.com) Tax Sale and Lien auctions. The collector scrapes category listing pages to discover auctions, then fetches individual detail pages to extract actual start/end dates for the calendar.

## Decisions

- **Fetcher**: Plain `httpx.AsyncClient` (no ScrapeClient) — server-rendered HTML, no bot protection observed
- **Extraction**: BeautifulSoup CSS selectors (deterministic, no LLM)
- **County**: Parse from title when possible, default to "Various"
- **Dates**: Two-pass approach — list pages for discovery, detail pages for actual start/end dates
- **Concurrency**: `asyncio.Semaphore(3)` for detail page fetches
- **Scope**: Start with unfiltered Tax Sale/Lien categories (all states), paginate. Switch to per-state URLs if pagination becomes unwieldy.

## Architecture

Single file: `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`

Subclasses `BaseCollector`. Follows the Bid4Assets pattern (httpx + BeautifulSoup, bypasses ScrapeClient).

### Two-Pass Fetch

**Pass 1 — List pages**: Fetch category pages for Tax Sale (`catid=1506`) and Lien (`catid=1505`). Paginate through all results. Extract per-auction: ID, state, title, source URL, and which category it came from.

**Pass 2 — Detail pages**: For each discovered auction, fetch `/sms/auction/view?auc={id}` to extract start and end dates. Capped at 3 concurrent requests via semaphore.

### List Page Parsing

Target HTML structure:
```html
<div class="auction-item" id="{auction_id}catGrid">
  <div class="auction-item-img">
    <a href="/sms/auction/view?auc={auction_id}">...</a>
    <span class="auction-item-state">MN</span>
  </div>
  <div class="auction-item-body px-0">
    <h6 class="card-title ...">
      <a href="..." title="#3946030 - 2025 Forfeiture Minimum Bid Sale: 25-5311-25765">
        #3946030 - 2025 Forfeiture Minimum Bid S...
      </a>
    </h6>
  </div>
</div>
```

Selectors:
- Auction items: `div.auction-item`
- Auction ID: `div.auction-item` `id` attribute, strip `catGrid` suffix
- State: `span.auction-item-state` text, stripped
- Title: `h6.card-title a` `title` attribute (full, untruncated)
- Source URL: constructed as `https://www.publicsurplus.com/sms/auction/view?auc={id}`

Pagination: follow "Next" link until absent.

### Detail Page Parsing

No research sample exists for the detail page yet. The parser will be built during implementation against a live fetch. Expected: look for date fields (start date, end date) in the auction details section of the page.

### County Extraction

Attempt to parse county name from the auction title using regex. Known patterns:
- "Norman County Tax-Forfeiture Parcel..." → "Norman"
- "Mohave County Land Sale..." → "Mohave"
- "Parcel 2 PIN#26-345-0510" → no match → "Various"

Pattern: `r'(\w[\w\s]*?)\s+County'` — extract the word(s) before "County".

If no match, set county to "Various".

### Normalization

Map to `Auction` model:
- `state`: from list page `.auction-item-state`
- `county`: from title regex or "Various"
- `start_date`: from detail page
- `end_date`: from detail page
- `sale_type`: `SaleType.DEED` for catid=1506 (Tax Sale), `SaleType.LIEN` for catid=1505
- `vendor`: `Vendor.PUBLIC_SURPLUS` (new enum value)
- `source_type`: `SourceType.VENDOR`
- `source_url`: detail page URL
- `confidence_score`: 0.80
- `notes`: auction title (for context, since county may be "Various")

### Enum Addition

Add `PUBLIC_SURPLUS = "PublicSurplus"` to the `Vendor` enum in `models/enums.py`.

## Error Handling

- **Empty categories**: Log info, continue (not an error)
- **Detail page fetch failures**: Log warning, skip that auction
- **Unparseable dates**: Skip the auction (no date = useless for calendar)
- **County regex misses**: Default to "Various"
- **HTTP 429 / 5xx**: Log and skip. No retry logic in v1.
- **Non-tax items**: Category filtering (catid=1506/1505) prevents most. Any that leak through come with "Various" county — harmless.

## Testing

- Unit tests for `parse_listing_html()` with saved HTML fixtures
- Unit tests for `parse_detail_html()` with saved HTML fixtures
- Unit tests for county extraction regex against known title patterns
- Unit test for `normalize()` mapping raw dicts to `Auction`
- Integration test against live site (marked `pytest.mark.integration`)

## References

- Issue: #57
- Research HTML: `data/research/sub/publicsurplus_recrawl.html`
- Research markdown: `data/research/sub/publicsurplus_recrawl.md`
- Crawl research: #52
