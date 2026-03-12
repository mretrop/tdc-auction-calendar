# State Agency Collectors Design (Issue #11)

## Overview

Implement collectors for four state agency sources (CO, CA, AR, IA), using Cloudflare Browser Rendering `/crawl` endpoint with `jsonOptions` as the primary extraction method and Crawl4AI + LLMExtraction as fallback.

## Infrastructure Changes

Small extensions to the existing scraping infra from issue #10:

### FetchResult

Add optional `json` field to `FetchResult` in `collectors/scraping/fetchers/protocol.py`:

```python
class FetchResult(BaseModel):
    url: str
    html: str | None = None
    markdown: str | None = None
    json: dict | list[dict] | None = None  # NEW: server-side extracted data
    status_code: int = Field(ge=100, le=599)
    fetcher: str
```

### CloudflareFetcher

Extend `fetch()` to accept optional `json_options` parameter:

```python
async def fetch(
    self, url: str, *, render_js: bool = True, json_options: dict | None = None
) -> FetchResult:
```

When `json_options` is provided:
- Add `"json"` to the `formats` list in the POST body
- Include `jsonOptions` key with the provided dict (contains `prompt` and `response_format`)
- In the poll response, extract `page.get("json")` from the completed result and assign to `FetchResult.json`

### Crawl4AiFetcher

Update `fetch()` signature to accept `json_options: dict | None = None` (ignored). This satisfies the updated `PageFetcher` protocol without changing behavior.

### PageFetcher Protocol

Add `json_options` as optional kwarg:

```python
class PageFetcher(Protocol):
    async def fetch(
        self, url: str, *, render_js: bool = True, json_options: dict | None = None
    ) -> FetchResult: ...
```

### ScrapeClient

Extend `scrape()` to accept and thread `json_options` through the full call chain:

```python
async def scrape(
    self,
    url: str,
    *,
    render_js: bool = True,
    extraction: ExtractionStrategy | None = None,
    schema: type[BaseModel] | None = None,
    json_options: dict | None = None,
) -> ScrapeResult:
```

**Threading:** `json_options` flows through the full internal call chain:
`scrape()` → `_fetch_with_fallback(url, render_js, json_options)` → `_fetch_with_retries(..., json_options)` → `fetcher.fetch(url, render_js=render_js, json_options=json_options)`

**Skip-extraction logic:** If `FetchResult.json` is already populated after fetching (either from fresh fetch or cache hit), use it directly as `ScrapeResult.data` and skip the extraction step. This applies to both the cache-hit path and the fresh-fetch path.

**Cache key:** Bypass cache when `json_options` is provided. In practice, the same URL won't be fetched with varying `json_options`, and caching pre-extracted JSON avoids stale-schema issues. A future enhancement could incorporate `json_options` into the cache key if needed.

## Collector Pattern

Each state agency collector follows a consistent shape:

- **Location:** `collectors/state_agencies/<state>.py` (~20-30 lines each)
- **Extends:** `BaseCollector`
- **Implements:** `name`, `source_type`, `_fetch()`, `normalize()`
- **Package:** Create `collectors/state_agencies/__init__.py` and update `collectors/__init__.py` to export new collectors

### Per-collector components

1. **Pydantic extraction schema** — source-specific fields (e.g., `ColoradoAuctionRecord` with `county`, `sale_date`, `sale_type`). Internal to the collector file, not exported.
2. **Extraction prompt** — natural language instruction for Cloudflare Workers AI (e.g., "Extract all county tax lien sale dates from this page").
3. **`json_options` construction:**
   ```python
   json_options = {
       "prompt": "Extract all county tax lien sale dates...",
       "response_format": ColoradoAuctionRecord.model_json_schema(),
   }
   ```
4. **`_fetch()` flow:**
   - Create `ScrapeClient` via `create_scrape_client()`
   - Build `json_options` from schema + prompt
   - Call `client.scrape(url, json_options=...)` — Cloudflare extracts server-side if available, otherwise falls back to Crawl4AI fetch + LLMExtraction
   - Expect `ScrapeResult.data` to be `list[dict]`. If single dict, wrap in list. If None, return empty list.
   - Call `self.normalize()` on each raw record
   - Log warnings for validation failures (no crash)
5. **`normalize()`** — maps source fields to `Auction` with `confidence_score=0.85`, `source_type=SourceType.STATE_AGENCY`

**Confidence score rationale:** 0.85 places state agency data above statutory (0.4) but below direct county website sources, reflecting the confidence tier hierarchy.

`BaseCollector.collect()` template method handles deduplication automatically.

## The Four Collectors

### Colorado (`colorado.py`) — cctpta.org/tax-lien-sales
- Cleanest source: HTML table of county sale dates
- Schema fields: `county`, `sale_date`, `sale_type` (all lien)
- Expected: >= 30 county records from fixture
- Build first as the pattern template

### California (`california.py`) — sco.ca.gov/ardtax_public_auction.html
- Single page covers all 58 counties
- Schema fields: `county`, `sale_date`, `auction_type`
- May have more complex formatting (notes, multi-day sales)

### Arkansas (`arkansas.py`) — cosl.org
- Centralized deed state authority
- Schema fields: `county`, `sale_date`, `sale_type` (all deed)
- Likely simpler structure

### Iowa (`iowa.py`) — iowatreasurers.org
- Representative lien state with statewide schedule
- Schema fields: `county`, `sale_date`, `sale_type` (all lien)

## Testing Strategy

No live HTTP in CI. All tests use recorded fixtures.

### Fixture files
- Located in `tests/fixtures/state_agencies/` — one JSON file per source (e.g., `colorado_cctpta.json`) containing pre-extracted data (what `ScrapeResult.data` returns)
- Tests mock `ScrapeClient`, not raw HTML parsing — so JSON fixtures are more appropriate than HTML fixtures

### Mock strategy
- Patch `create_scrape_client` to return a mock `ScrapeClient`
- Mock returns `ScrapeResult` with pre-loaded extracted data (simulating either Cloudflare or fallback path)
- Tests verify the collector's `normalize()` logic and error handling, not the scraping infra (already tested in issue #10)

### Test cases per collector
- **Happy path:** fixture → expected number of `Auction` records with correct fields
- **Validation errors:** malformed records logged as warnings, not crashes
- **Empty/missing data:** returns empty list, no exception
- **CO specifically:** >= 30 county records (per acceptance criteria)

### Infrastructure tests
- `FetchResult.json` field: serialization, optional behavior
- `CloudflareFetcher.json_options`: passed to POST body, parsed from response
- `ScrapeClient` json_options threading through `_fetch_with_fallback` → `_fetch_with_retries` → `fetcher.fetch()`
- Skip-extraction logic: when `FetchResult.json` populated (both cache-hit and fresh-fetch paths)
- Cache bypass when `json_options` provided
- `Crawl4AiFetcher` accepts and ignores `json_options`

## Acceptance Criteria (from issue #11)

- [ ] Each collector extends `BaseCollector`
- [ ] Each tested with recorded HTML fixtures (no live HTTP in CI)
- [ ] Handles format changes gracefully (logs warning, does not crash)
- [ ] CO returns >= 30 county records from fixture
