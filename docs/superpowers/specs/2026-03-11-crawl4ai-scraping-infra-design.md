# Crawl4AI Integration + Shared Scraping Infrastructure

**Issue:** #10 — [M2] Crawl4AI integration + shared scraping infrastructure
**Date:** 2026-03-11
**Status:** Draft

## Problem

Downstream collectors (#11–13) need a shared way to fetch rendered web pages from county/state auction sites and extract structured data. Sites range from simple HTML tables to JS-heavy vendor platforms (RealAuction, Bid4Assets). The system must be reliable, respect rate limits, cache responses, and support both LLM-based and CSS-based extraction.

## Decision: Abstract Renderer with Dual Backends

Rather than coupling to a single scraping engine, we define a `PageFetcher` protocol with two implementations:

- **CloudflareFetcher** (primary) — cloud-hosted browser rendering via the Cloudflare `/crawl` REST API. Most reliable: no local Chromium, no memory/crash issues.
- **Crawl4AiFetcher** (fallback) — local headless browser via Crawl4AI's `AsyncWebCrawler`. Works offline, useful for local dev.

Extraction (LLM or CSS) is a separate layer that operates on fetched content regardless of which backend produced it. Collectors interact only with `ScrapeClient`, which orchestrates fetching, caching, rate limiting, retries, and extraction behind a single `scrape()` method.

## Module Structure

```
src/tdc_auction_calendar/collectors/
├── base.py                          # existing BaseCollector (unchanged)
├── scraping/
│   ├── __init__.py                  # re-exports ScrapeClient, ScrapeResult, create_scrape_client
│   ├── client.py                    # ScrapeClient + create_scrape_client factory
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── protocol.py              # PageFetcher Protocol + FetchResult model
│   │   ├── cloudflare.py            # CloudflareFetcher
│   │   └── crawl4ai.py              # Crawl4AiFetcher
│   └── extraction.py                # LLMExtraction + CSSExtraction strategies
├── statutory/
│   └── ...                          # existing (unchanged)
```

## Core Interfaces

### FetchResult and PageFetcher Protocol

```python
# fetchers/protocol.py
from pydantic import BaseModel
from typing import Protocol

class FetchResult(BaseModel):
    url: str
    html: str | None = None
    markdown: str | None = None
    status_code: int
    fetcher: str  # "cloudflare" or "crawl4ai"

class PageFetcher(Protocol):
    async def fetch(self, url: str, *, render_js: bool = True) -> FetchResult: ...
```

### ScrapeClient

```python
# client.py
class ScrapeClient:
    def __init__(
        self,
        primary: PageFetcher,
        fallback: PageFetcher | None,
        rate_limiter: RateLimiter,
        cache: ResponseCache,
    ): ...

    async def scrape(
        self,
        url: str,
        *,
        render_js: bool = True,
        extraction: ExtractionStrategy | None = None,
        schema: type[BaseModel] | None = None,
    ) -> ScrapeResult: ...
```

### ScrapeResult

```python
class ScrapeResult(BaseModel):
    fetch: FetchResult
    data: BaseModel | dict | None = None  # extracted structured data
    from_cache: bool = False
```

### ExtractionStrategy Protocol

```python
# extraction.py
class ExtractionStrategy(Protocol):
    async def extract(self, content: str, **kwargs) -> dict | BaseModel: ...
```

## Fetcher Backends

### CloudflareFetcher

- POST to `https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering/crawl`
- Uses `httpx.AsyncClient` for HTTP calls
- Reads `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` from environment
- Requests `markdown` + `html` formats
- Handles the async job flow internally: POST to start, poll with GET until complete
- `render_js` maps to Cloudflare's `render` parameter

### Crawl4AiFetcher

- Wraps Crawl4AI's `AsyncWebCrawler`
- Returns rendered HTML + markdown from the crawler response
- Used as fallback when Cloudflare is unavailable, or as primary for local development

## ScrapeClient Flow

When `scrape()` is called:

1. **Cache check** — look up (URL + render_js) hash in file cache. If hit and not expired, skip to step 6.
2. **Rate limit** — wait if another request to this domain was made within the per-domain delay window.
3. **Primary fetch** — call primary fetcher (Cloudflare by default).
4. **Retry on failure** — exponential backoff, max 3 retries, base delay 1s with jitter. Only retries transient errors (network, 5xx), not 4xx.
5. **Fallback** — if primary exhausts retries and a fallback fetcher is configured, try fallback with the same retry policy.
6. **Cache store** — write raw response to `data/cache/` with TTL metadata.
7. **Extract** — if an extraction strategy was provided, run it on the fetched markdown (preferred) or HTML.
8. **Return** — `ScrapeResult` with raw content, extracted data, and cache status.

All steps are logged via structlog (cache hit/miss, fetcher used, retry attempts, extraction method).

## Rate Limiter

- Per-domain delay: configurable, default 2 seconds between requests to the same domain.
- Collectors can override per-domain delays, e.g., `rate_limits={"realauction.com": 5.0}`.
- Implementation: tracks last request timestamp per domain, async sleep for remaining delay.

## Response Cache

- File-based cache in `data/cache/` (configurable via `SCRAPE_CACHE_DIR`).
- Cache key: SHA-256 hash of `(url, render_js)`.
- TTL: configurable, default 6 hours.
- Stores `FetchResult` as JSON with a metadata header containing the expiry timestamp.
- Cache hits and misses logged via structlog.

## Extraction Strategies

### LLMExtraction

- Uses the `anthropic` SDK directly (not Crawl4AI's built-in LLM extraction) to keep extraction decoupled from fetching.
- Default model: `claude-sonnet-4-20250514` — good cost/quality balance for parsing auction tables.
- Uses Claude's tool_use feature to extract structured data matching a Pydantic schema.
- Reads `ANTHROPIC_API_KEY` from environment.

### CSSExtraction

- CSS selector-based extraction for well-structured pages.
- Accepts a mapping of field names to CSS selectors, e.g., `{"date": "td.auction-date", "county": "td.county-name"}`.
- Uses a lightweight HTML parser.
- No LLM cost — suitable for sites with consistent, predictable markup.

### Collector choice

Each collector chooses its extraction strategy when calling `scrape()`. LLM extraction is the default for messy county sites; CSS extraction is available for well-structured pages where it saves cost and latency.

## Configuration

All configuration via environment variables with sensible defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLOUDFLARE_ACCOUNT_ID` | (required for Cloudflare) | Cloudflare account ID |
| `CLOUDFLARE_API_TOKEN` | (required for Cloudflare) | API token with Browser Rendering permission |
| `ANTHROPIC_API_KEY` | (required for LLM extraction) | Anthropic API key |
| `SCRAPE_CACHE_DIR` | `data/cache` | Cache directory path |
| `SCRAPE_CACHE_TTL` | `21600` (6h) | Cache TTL in seconds |
| `SCRAPE_RATE_LIMIT_DEFAULT` | `2.0` | Default per-domain delay in seconds |
| `SCRAPE_RETRY_MAX` | `3` | Max retry attempts per fetcher |
| `SCRAPE_RETRY_BASE_DELAY` | `1.0` | Base retry delay in seconds |
| `SCRAPE_CONNECT_TIMEOUT` | `30` | Connection timeout in seconds |
| `SCRAPE_READ_TIMEOUT` | `60` | Read timeout in seconds |

### Client Factory

```python
def create_scrape_client() -> ScrapeClient:
    """Build a ScrapeClient with default config from env vars.

    If Cloudflare credentials are present, uses CloudflareFetcher as primary
    and Crawl4AiFetcher as fallback. Otherwise, uses Crawl4AiFetcher as primary
    with no fallback.
    """
```

Collectors call `create_scrape_client()` for default wiring. Tests construct `ScrapeClient` directly with mocked fetchers.

## Testing Strategy

No real HTTP calls in any test. All external I/O is mocked.

- **CloudflareFetcher:** Mocked httpx responses simulating the Cloudflare API job flow (POST → poll → results).
- **Crawl4AiFetcher:** Patched `AsyncWebCrawler` returning fixture HTML/markdown.
- **Rate limiter:** Mock clock to verify per-domain delays without real sleeps.
- **Retry logic:** Mock error responses — verify transient errors trigger retries, permanent errors (4xx) do not.
- **Cache:** Temp directory — verify cache writes, hits, misses, TTL expiry. Verify structlog output.
- **LLMExtraction:** Mocked Anthropic client returning fixture extraction results.
- **CSSExtraction:** Sample HTML fixtures with known structure.
- **ScrapeClient integration:** End-to-end with all mocked backends — verify primary→fallback flow, cache interaction, rate limiting, extraction pipeline.

## Dependencies

No new dependencies required. Already in `pyproject.toml`:
- `crawl4ai>=0.4` — for Crawl4AiFetcher
- `httpx>=0.27` — for CloudflareFetcher API calls
- `anthropic>=0.40` — for LLM extraction
- `structlog>=24.0` — for logging
- `pydantic>=2.0` — for schemas and models

HTML parsing for CSS extraction: evaluate whether crawl4ai's built-in parser or `beautifulsoup4` (new dependency) is more appropriate during implementation.

## Out of Scope

- Actual collector implementations (issues #11–13)
- Collector orchestrator (issue #15)
- Claude API fallback parser as a standalone component (issue #14) — though LLMExtraction here is related, #14 covers the fallback parsing logic for when structured extraction fails entirely
