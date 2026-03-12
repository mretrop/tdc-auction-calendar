# State Agency Collectors Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement four state agency collectors (CO, CA, AR, IA) with Cloudflare JSON extraction as primary and Crawl4AI + LLMExtraction as fallback.

**Architecture:** Extend the existing scraping infra (FetchResult, CloudflareFetcher, ScrapeClient) to support Cloudflare's `jsonOptions` parameter for server-side extraction. Each collector extends `BaseCollector`, defines a Pydantic extraction schema + prompt, and uses `ScrapeClient.scrape()` with `json_options`. The fallback path (Crawl4AI + LLMExtraction) activates automatically when Cloudflare is unavailable.

**Tech Stack:** Python, Pydantic, Crawl4AI, Cloudflare Browser Rendering API, structlog, pytest

**Spec:** `docs/superpowers/specs/2026-03-12-state-agency-collectors-design.md`

---

## File Structure

### Modified files
| File | Responsibility |
|------|---------------|
| `src/tdc_auction_calendar/collectors/scraping/fetchers/protocol.py` | Add `json` field to `FetchResult`, add `json_options` to `PageFetcher` protocol |
| `src/tdc_auction_calendar/collectors/scraping/fetchers/cloudflare.py` | Accept `json_options`, include in POST body, parse `json` from response |
| `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py` | Accept and ignore `json_options` kwarg |
| `src/tdc_auction_calendar/collectors/scraping/client.py` | Thread `json_options` through `scrape()` → `_fetch_with_fallback()` → `_fetch_with_retries()` → `fetcher.fetch()`. Skip extraction when `FetchResult.json` populated. Bypass cache when `json_options` provided. |
| `src/tdc_auction_calendar/collectors/__init__.py` | Export new collectors |

### New files
| File | Responsibility |
|------|---------------|
| `src/tdc_auction_calendar/collectors/state_agencies/__init__.py` | Package init, export all four collectors |
| `src/tdc_auction_calendar/collectors/state_agencies/colorado.py` | Colorado collector (CCTPTA) |
| `src/tdc_auction_calendar/collectors/state_agencies/california.py` | California collector (SCO) |
| `src/tdc_auction_calendar/collectors/state_agencies/arkansas.py` | Arkansas collector (COSL) |
| `src/tdc_auction_calendar/collectors/state_agencies/iowa.py` | Iowa collector |
| `tests/scraping/test_json_options.py` | Tests for json_options infra changes |
| `tests/collectors/state_agencies/__init__.py` | Test package init |
| `tests/collectors/state_agencies/test_colorado.py` | Colorado collector tests |
| `tests/collectors/state_agencies/test_california.py` | California collector tests |
| `tests/collectors/state_agencies/test_arkansas.py` | Arkansas collector tests |
| `tests/collectors/state_agencies/test_iowa.py` | Iowa collector tests |
| `tests/fixtures/state_agencies/colorado_cctpta.json` | Fixture: extracted data for CO |
| `tests/fixtures/state_agencies/california_sco.json` | Fixture: extracted data for CA |
| `tests/fixtures/state_agencies/arkansas_cosl.json` | Fixture: extracted data for AR |
| `tests/fixtures/state_agencies/iowa_treasurers.json` | Fixture: extracted data for IA |

---

## Chunk 1: Infrastructure — json_options support

### Task 1: Add `json` field to FetchResult

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/fetchers/protocol.py:10-19`
- Test: `tests/scraping/test_protocol.py`

- [ ] **Step 1: Write failing test for FetchResult.json field**

```python
# Append to tests/scraping/test_protocol.py

def test_fetch_result_with_json():
    """FetchResult accepts optional json field."""
    result = FetchResult(
        url="https://example.com",
        status_code=200,
        fetcher="cloudflare",
        json=[{"county": "Adams", "sale_date": "2026-06-15"}],
    )
    assert result.json == [{"county": "Adams", "sale_date": "2026-06-15"}]


def test_fetch_result_json_defaults_none():
    """FetchResult.json defaults to None."""
    result = FetchResult(url="https://example.com", status_code=200, fetcher="cloudflare")
    assert result.json is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scraping/test_protocol.py::test_fetch_result_with_json -v`
Expected: FAIL — `json` field not recognized

- [ ] **Step 3: Add json field to FetchResult**

In `src/tdc_auction_calendar/collectors/scraping/fetchers/protocol.py`, change:

```python
class FetchResult(BaseModel):
    """Result of fetching a single URL."""

    model_config = {"frozen": True}

    url: str
    html: str | None = None
    markdown: str | None = None
    status_code: int = Field(ge=100, le=599)
    fetcher: str  # "cloudflare" or "crawl4ai"
```

to:

```python
class FetchResult(BaseModel):
    """Result of fetching a single URL."""

    model_config = {"frozen": True}

    url: str
    html: str | None = None
    markdown: str | None = None
    json: dict | list[dict] | None = None
    status_code: int = Field(ge=100, le=599)
    fetcher: str  # "cloudflare" or "crawl4ai"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scraping/test_protocol.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/fetchers/protocol.py tests/scraping/test_protocol.py
git commit -m "feat(scraping): add json field to FetchResult for server-side extraction (issue #11)"
```

---

### Task 2: Add `json_options` to PageFetcher protocol and Crawl4AiFetcher

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/fetchers/protocol.py:22-27`
- Modify: `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py:31`
- Test: `tests/scraping/test_json_options.py` (new)

- [ ] **Step 1: Write failing test that passes json_options to Crawl4AI**

Create `tests/scraping/test_json_options.py`:

```python
"""Tests for json_options infrastructure support."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import Crawl4AiFetcher
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult


async def test_crawl4ai_accepts_and_ignores_json_options():
    """Crawl4AiFetcher accepts json_options kwarg without error."""
    mock_crawler = AsyncMock()
    mock_result = MagicMock()
    mock_result.status_code = 200
    mock_result.html = "<h1>Test</h1>"
    mock_result.markdown = "# Test"
    mock_crawler.arun.return_value = mock_result

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    result = await fetcher.fetch(
        "https://example.com",
        json_options={"prompt": "Extract data", "response_format": {}},
    )

    assert result.status_code == 200
    assert result.json is None  # Crawl4AI does not do JSON extraction
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scraping/test_json_options.py::test_crawl4ai_accepts_and_ignores_json_options -v`
Expected: FAIL — `fetch() got an unexpected keyword argument 'json_options'`

- [ ] **Step 3: Update PageFetcher protocol and Crawl4AiFetcher**

In `src/tdc_auction_calendar/collectors/scraping/fetchers/protocol.py`, change:

```python
class PageFetcher(Protocol):
    """Protocol for page-fetching backends."""

    async def fetch(self, url: str, *, render_js: bool = True) -> FetchResult: ...

    async def close(self) -> None: ...
```

to:

```python
class PageFetcher(Protocol):
    """Protocol for page-fetching backends."""

    async def fetch(
        self, url: str, *, render_js: bool = True, json_options: dict | None = None
    ) -> FetchResult: ...

    async def close(self) -> None: ...
```

In `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py`, change line 31:

```python
    async def fetch(self, url: str, *, render_js: bool = True) -> FetchResult:
```

to:

```python
    async def fetch(
        self, url: str, *, render_js: bool = True, json_options: dict | None = None
    ) -> FetchResult:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_json_options.py tests/scraping/test_protocol.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `uv run pytest`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/fetchers/protocol.py src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py tests/scraping/test_json_options.py
git commit -m "feat(scraping): add json_options to PageFetcher protocol and Crawl4AiFetcher (issue #11)"
```

---

### Task 3: Add `json_options` to CloudflareFetcher

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/fetchers/cloudflare.py:50-117`
- Test: `tests/scraping/test_cloudflare.py`
- Test: `tests/scraping/test_json_options.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/scraping/test_json_options.py`:

```python
import httpx
from unittest.mock import patch

from tdc_auction_calendar.collectors.scraping.fetchers.cloudflare import CloudflareFetcher


@pytest.fixture()
def cf_fetcher():
    return CloudflareFetcher(account_id="test-account", api_token="test-token")


async def test_cloudflare_json_options_in_post_body(cf_fetcher):
    """json_options adds 'json' to formats and 'jsonOptions' to POST body."""
    json_options = {
        "prompt": "Extract county tax sale dates",
        "response_format": {"type": "object", "properties": {"county": {"type": "string"}}},
    }

    mock_post_resp = httpx.Response(200, json={"id": "job-1"})
    mock_poll_resp = httpx.Response(200, json={
        "status": "completed",
        "result": [{
            "url": "https://example.com",
            "html": "<h1>Sales</h1>",
            "markdown": "# Sales",
            "json": [{"county": "Adams"}],
            "metadata": {"statusCode": 200},
        }],
    })

    with patch.object(cf_fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = mock_post_resp
        mock_http.get.return_value = mock_poll_resp

        result = await cf_fetcher.fetch("https://example.com", json_options=json_options)

    # Verify POST body includes json format and jsonOptions
    call_kwargs = mock_http.post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert "json" in body["formats"]
    assert body["jsonOptions"] == json_options

    # Verify FetchResult has json data
    assert result.json == [{"county": "Adams"}]


async def test_cloudflare_no_json_options_unchanged(cf_fetcher):
    """Without json_options, CloudflareFetcher behaves as before."""
    mock_post_resp = httpx.Response(200, json={"id": "job-1"})
    mock_poll_resp = httpx.Response(200, json={
        "status": "completed",
        "result": [{
            "url": "https://example.com",
            "html": "<h1>Sales</h1>",
            "markdown": "# Sales",
            "metadata": {"statusCode": 200},
        }],
    })

    with patch.object(cf_fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = mock_post_resp
        mock_http.get.return_value = mock_poll_resp

        result = await cf_fetcher.fetch("https://example.com")

    # Verify POST body does NOT include json format
    call_kwargs = mock_http.post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert "json" not in body["formats"]
    assert "jsonOptions" not in body

    assert result.json is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_json_options.py::test_cloudflare_json_options_in_post_body -v`
Expected: FAIL — `fetch() got an unexpected keyword argument 'json_options'`

- [ ] **Step 3: Implement json_options in CloudflareFetcher**

In `src/tdc_auction_calendar/collectors/scraping/fetchers/cloudflare.py`, change the `fetch` method signature and POST body:

Change line 50:
```python
    async def fetch(self, url: str, *, render_js: bool = True) -> FetchResult:
```
to:
```python
    async def fetch(
        self, url: str, *, render_js: bool = True, json_options: dict | None = None
    ) -> FetchResult:
```

Change the POST body (lines 57-62):
```python
            json={
                "url": url,
                "formats": ["markdown", "html"],
                "render": render_js,
                "limit": 1,
            },
```
to:
```python
            json=self._build_post_body(url, render_js, json_options),
```

Add the helper method before `fetch`:
```python
    @staticmethod
    def _build_post_body(
        url: str, render_js: bool, json_options: dict | None
    ) -> dict:
        body: dict = {
            "url": url,
            "formats": ["markdown", "html"],
            "render": render_js,
            "limit": 1,
        }
        if json_options is not None:
            body["formats"].append("json")
            body["jsonOptions"] = json_options
        return body
```

Change the FetchResult construction in the completed branch (lines 111-117):
```python
                return FetchResult(
                    url=url,
                    html=page.get("html"),
                    markdown=page.get("markdown"),
                    status_code=status_code,
                    fetcher="cloudflare",
                )
```
to:
```python
                return FetchResult(
                    url=url,
                    html=page.get("html"),
                    markdown=page.get("markdown"),
                    json=page.get("json"),
                    status_code=status_code,
                    fetcher="cloudflare",
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_json_options.py tests/scraping/test_cloudflare.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/fetchers/cloudflare.py tests/scraping/test_json_options.py
git commit -m "feat(scraping): add json_options support to CloudflareFetcher (issue #11)"
```

---

### Task 4: Thread `json_options` through ScrapeClient

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/client.py:109-218`
- Test: `tests/scraping/test_json_options.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/scraping/test_json_options.py`:

```python
from tdc_auction_calendar.collectors.scraping.client import ScrapeClient, ScrapeResult
from tdc_auction_calendar.collectors.scraping.cache import ResponseCache
from tdc_auction_calendar.collectors.scraping.rate_limiter import RateLimiter


def _make_fetcher(fetch_result):
    fetcher = AsyncMock()
    fetcher.fetch.return_value = fetch_result
    fetcher.close = AsyncMock()
    return fetcher


async def test_scrape_threads_json_options_to_fetcher():
    """json_options is passed through to fetcher.fetch()."""
    result = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html="<h1>Data</h1>", json=[{"county": "Adams"}],
    )
    fetcher = _make_fetcher(result)
    client = ScrapeClient(primary=fetcher, rate_limiter=RateLimiter(default_delay=0.0))

    json_opts = {"prompt": "Extract data", "response_format": {}}
    scrape_result = await client.scrape("https://example.com", json_options=json_opts)

    fetcher.fetch.assert_called_once_with(
        "https://example.com", render_js=True, json_options=json_opts,
    )
    assert scrape_result.data == [{"county": "Adams"}]


async def test_scrape_skips_extraction_when_json_populated():
    """When FetchResult.json is populated, extraction is skipped."""
    result = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html="<h1>Data</h1>", json=[{"county": "Adams"}],
    )
    fetcher = _make_fetcher(result)
    mock_extraction = AsyncMock()
    client = ScrapeClient(primary=fetcher, rate_limiter=RateLimiter(default_delay=0.0))

    scrape_result = await client.scrape(
        "https://example.com",
        json_options={"prompt": "Extract", "response_format": {}},
        extraction=mock_extraction,
    )

    mock_extraction.extract.assert_not_called()
    assert scrape_result.data == [{"county": "Adams"}]


async def test_scrape_falls_back_to_extraction_when_json_none():
    """When FetchResult.json is None, extraction runs normally."""
    result = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html="<h1>Data</h1>", markdown="# Data",
    )
    fetcher = _make_fetcher(result)
    mock_extraction = AsyncMock()
    mock_extraction.extract.return_value = [{"county": "Adams"}]
    client = ScrapeClient(primary=fetcher, rate_limiter=RateLimiter(default_delay=0.0))

    scrape_result = await client.scrape(
        "https://example.com",
        extraction=mock_extraction,
    )

    mock_extraction.extract.assert_called_once()
    assert scrape_result.data == [{"county": "Adams"}]


async def test_scrape_bypasses_cache_when_json_options_provided(tmp_path):
    """Cache is bypassed when json_options is provided."""
    # Pre-populate cache with a result that has no json
    cache = ResponseCache(cache_dir=str(tmp_path), ttl=3600)
    cached_result = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html="<h1>Old</h1>",
    )
    await cache.put("https://example.com", True, cached_result)

    # Fetcher returns fresh result with json
    fresh_result = FetchResult(
        url="https://example.com", status_code=200, fetcher="primary",
        html="<h1>New</h1>", json=[{"county": "Adams"}],
    )
    fetcher = _make_fetcher(fresh_result)
    client = ScrapeClient(
        primary=fetcher, rate_limiter=RateLimiter(default_delay=0.0), cache=cache,
    )

    scrape_result = await client.scrape(
        "https://example.com",
        json_options={"prompt": "Extract", "response_format": {}},
    )

    # Should have fetched fresh, not used cache
    assert scrape_result.from_cache is False
    assert scrape_result.data == [{"county": "Adams"}]
    fetcher.fetch.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_json_options.py::test_scrape_threads_json_options_to_fetcher -v`
Expected: FAIL — `scrape() got an unexpected keyword argument 'json_options'`

- [ ] **Step 3: Implement json_options threading in ScrapeClient**

In `src/tdc_auction_calendar/collectors/scraping/client.py`:

**Update `scrape()` signature** (line 109-116) — add `json_options` parameter:
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

**Update `scrape()` body** — bypass cache when json_options, thread json_options, skip extraction when json populated. Replace lines 117-144 with:
```python
        """Fetch a URL, cache the result, and optionally extract structured data."""
        # 1. Cache check (bypass when json_options provided)
        if self._cache is not None and json_options is None:
            cached = await self._cache.get(url, render_js)
            if cached is not None:
                data = None
                if cached.json is not None:
                    data = cached.json
                elif extraction is not None or schema is not None:
                    data = await self._run_extraction(cached, extraction, schema)
                return ScrapeResult(fetch=cached, data=data, from_cache=True)

        # 2. Rate limit
        domain = urlparse(url).netloc
        await self._rate_limiter.wait(domain)

        # 3-5. Fetch with retries and fallback
        fetch_result = await self._fetch_with_fallback(url, render_js, json_options)

        # 6. Cache store (skip when json_options to avoid stale schema data)
        if self._cache is not None and json_options is None:
            await self._cache.put(url, render_js, fetch_result)

        # 7. Extract (skip if server-side JSON already populated)
        data = None
        if fetch_result.json is not None:
            data = fetch_result.json
        elif extraction is not None or schema is not None:
            data = await self._run_extraction(fetch_result, extraction, schema)

        # 8. Return
        return ScrapeResult(fetch=fetch_result, data=data, from_cache=False)
```

**Update `_fetch_with_fallback()`** (line 146-160) — accept and pass json_options:
```python
    async def _fetch_with_fallback(
        self, url: str, render_js: bool, json_options: dict | None = None,
    ) -> FetchResult:
        """Try primary fetcher with retries, then fallback."""
        attempts: list[dict] = []

        for fetcher_name, fetcher in [("primary", self._primary), ("fallback", self._fallback)]:
            if fetcher is None:
                continue

            result = await self._fetch_with_retries(
                fetcher, fetcher_name, url, render_js, attempts, json_options,
            )
            if result is not None:
                return result

        raise ScrapeError(url=url, attempts=attempts)
```

**Update `_fetch_with_retries()`** (line 162-218) — accept and pass json_options:
```python
    async def _fetch_with_retries(
        self,
        fetcher: PageFetcher,
        fetcher_name: str,
        url: str,
        render_js: bool,
        attempts: list[dict],
        json_options: dict | None = None,
    ) -> FetchResult | None:
```

And change the fetch call on line 177:
```python
                result = await fetcher.fetch(url, render_js=render_js)
```
to:
```python
                result = await fetcher.fetch(
                    url, render_js=render_js, json_options=json_options,
                )
```

- [ ] **Step 4: Run json_options tests**

Run: `uv run pytest tests/scraping/test_json_options.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `uv run pytest`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/client.py tests/scraping/test_json_options.py
git commit -m "feat(scraping): thread json_options through ScrapeClient with cache bypass and skip-extraction (issue #11)"
```

---

## Chunk 2: Colorado Collector (pattern template)

### Task 5: Create state_agencies package and Colorado collector

**Files:**
- Create: `src/tdc_auction_calendar/collectors/state_agencies/__init__.py`
- Create: `src/tdc_auction_calendar/collectors/state_agencies/colorado.py`
- Create: `tests/fixtures/state_agencies/colorado_cctpta.json`
- Create: `tests/collectors/__init__.py` (if not exists)
- Create: `tests/collectors/state_agencies/__init__.py`
- Create: `tests/collectors/state_agencies/test_colorado.py`

- [ ] **Step 1: Create fixture data**

Create `tests/fixtures/state_agencies/colorado_cctpta.json` with realistic extracted data (what Cloudflare's JSON extraction would return). This represents the `ScrapeResult.data` that comes back from the scrape:

```json
[
  {"county": "Adams", "sale_date": "2026-11-01", "sale_type": "lien"},
  {"county": "Alamosa", "sale_date": "2026-11-15", "sale_type": "lien"},
  {"county": "Arapahoe", "sale_date": "2026-11-01", "sale_type": "lien"},
  {"county": "Archuleta", "sale_date": "2026-11-05", "sale_type": "lien"},
  {"county": "Baca", "sale_date": "2026-12-01", "sale_type": "lien"},
  {"county": "Bent", "sale_date": "2026-11-10", "sale_type": "lien"},
  {"county": "Boulder", "sale_date": "2026-11-01", "sale_type": "lien"},
  {"county": "Broomfield", "sale_date": "2026-11-01", "sale_type": "lien"},
  {"county": "Chaffee", "sale_date": "2026-11-15", "sale_type": "lien"},
  {"county": "Cheyenne", "sale_date": "2026-12-01", "sale_type": "lien"},
  {"county": "Clear Creek", "sale_date": "2026-11-10", "sale_type": "lien"},
  {"county": "Conejos", "sale_date": "2026-11-15", "sale_type": "lien"},
  {"county": "Costilla", "sale_date": "2026-11-15", "sale_type": "lien"},
  {"county": "Crowley", "sale_date": "2026-11-05", "sale_type": "lien"},
  {"county": "Custer", "sale_date": "2026-11-15", "sale_type": "lien"},
  {"county": "Delta", "sale_date": "2026-11-10", "sale_type": "lien"},
  {"county": "Denver", "sale_date": "2026-11-01", "sale_type": "lien"},
  {"county": "Dolores", "sale_date": "2026-12-01", "sale_type": "lien"},
  {"county": "Douglas", "sale_date": "2026-11-01", "sale_type": "lien"},
  {"county": "Eagle", "sale_date": "2026-11-05", "sale_type": "lien"},
  {"county": "El Paso", "sale_date": "2026-11-01", "sale_type": "lien"},
  {"county": "Elbert", "sale_date": "2026-11-10", "sale_type": "lien"},
  {"county": "Fremont", "sale_date": "2026-11-10", "sale_type": "lien"},
  {"county": "Garfield", "sale_date": "2026-11-05", "sale_type": "lien"},
  {"county": "Gilpin", "sale_date": "2026-11-15", "sale_type": "lien"},
  {"county": "Grand", "sale_date": "2026-11-15", "sale_type": "lien"},
  {"county": "Gunnison", "sale_date": "2026-11-10", "sale_type": "lien"},
  {"county": "Huerfano", "sale_date": "2026-11-15", "sale_type": "lien"},
  {"county": "Jefferson", "sale_date": "2026-11-01", "sale_type": "lien"},
  {"county": "Kit Carson", "sale_date": "2026-12-01", "sale_type": "lien"},
  {"county": "Lake", "sale_date": "2026-11-10", "sale_type": "lien"},
  {"county": "Larimer", "sale_date": "2026-11-01", "sale_type": "lien"},
  {"county": "Mesa", "sale_date": "2026-11-05", "sale_type": "lien"},
  {"county": "Pueblo", "sale_date": "2026-11-01", "sale_type": "lien"},
  {"county": "Weld", "sale_date": "2026-11-01", "sale_type": "lien"}
]
```

- [ ] **Step 2: Write failing tests**

Create `tests/collectors/state_agencies/__init__.py` (empty file).
Create `tests/collectors/__init__.py` (empty file, if not exists).

Create `tests/collectors/state_agencies/test_colorado.py`:

```python
"""Tests for Colorado state agency collector."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.state_agencies.colorado import ColoradoCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "state_agencies"


def _load_fixture():
    return json.loads((FIXTURES_DIR / "colorado_cctpta.json").read_text())


def _mock_scrape_result(data):
    return ScrapeResult(
        fetch=FetchResult(
            url="https://cctpta.org/tax-lien-sales",
            status_code=200,
            fetcher="cloudflare",
            html="<table>...</table>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return ColoradoCollector()


def test_name(collector):
    assert collector.name == "colorado_state_agency"


def test_source_type(collector):
    assert collector.source_type == SourceType.STATE_AGENCY


def test_normalize_valid_record(collector):
    raw = {"county": "Adams", "sale_date": "2026-11-01", "sale_type": "lien"}
    auction = collector.normalize(raw)
    assert auction.state == "CO"
    assert auction.county == "Adams"
    assert auction.start_date == date(2026, 11, 1)
    assert auction.sale_type == SaleType.LIEN
    assert auction.source_type == SourceType.STATE_AGENCY
    assert auction.confidence_score == 0.85
    assert auction.source_url == "https://cctpta.org/tax-lien-sales"


def test_normalize_missing_county_raises(collector):
    raw = {"sale_date": "2026-11-01", "sale_type": "lien"}  # missing county key
    with pytest.raises((ValidationError, ValueError, KeyError)):
        collector.normalize(raw)


def test_normalize_invalid_date_raises(collector):
    raw = {"county": "Adams", "sale_date": "not-a-date", "sale_type": "lien"}
    with pytest.raises((ValidationError, ValueError)):
        collector.normalize(raw)


async def test_fetch_returns_auctions(collector):
    fixture_data = _load_fixture()
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(fixture_data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.colorado.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) >= 30
    assert all(a.state == "CO" for a in auctions)
    assert all(a.source_type == SourceType.STATE_AGENCY for a in auctions)


async def test_fetch_empty_data_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(None)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.colorado.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_fetch_skips_invalid_records(collector):
    data = [
        {"county": "Adams", "sale_date": "2026-11-01", "sale_type": "lien"},
        {"county": "", "sale_date": "bad-date"},  # invalid
        {"county": "Boulder", "sale_date": "2026-11-01", "sale_type": "lien"},
    ]
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.colorado.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/state_agencies/test_colorado.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tdc_auction_calendar.collectors.state_agencies'`

- [ ] **Step 4: Implement ColoradoCollector**

Create `src/tdc_auction_calendar/collectors/state_agencies/__init__.py`:

```python
from tdc_auction_calendar.collectors.state_agencies.colorado import ColoradoCollector

__all__ = ["ColoradoCollector"]
```

Create `src/tdc_auction_calendar/collectors/state_agencies/colorado.py`:

```python
"""Colorado state agency collector — CCTPTA tax lien sales."""

from __future__ import annotations

from datetime import date

import structlog
from pydantic import BaseModel

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import create_scrape_client
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType

logger = structlog.get_logger()

_URL = "https://cctpta.org/tax-lien-sales"
_PROMPT = "Extract all county tax lien sale dates from this page. Each row should have county name, sale date, and sale type."


class ColoradoAuctionRecord(BaseModel):
    county: str
    sale_date: str
    sale_type: str = "lien"


class ColoradoCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "colorado_state_agency"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATE_AGENCY

    async def _fetch(self) -> list[Auction]:
        json_options = {
            "prompt": _PROMPT,
            "response_format": ColoradoAuctionRecord.model_json_schema(),
        }
        client = create_scrape_client()
        try:
            result = await client.scrape(_URL, json_options=json_options)
        finally:
            await client.close()

        raw_records = result.data if isinstance(result.data, list) else (
            [result.data] if result.data is not None else []
        )

        auctions = []
        for raw in raw_records:
            try:
                auctions.append(self.normalize(raw))
            except Exception as exc:
                logger.warning(
                    "normalize_failed",
                    collector=self.name,
                    raw=raw,
                    error=str(exc),
                )
        return auctions

    def normalize(self, raw: dict) -> Auction:
        return Auction(
            state="CO",
            county=raw["county"],
            start_date=date.fromisoformat(raw["sale_date"]),
            sale_type=SaleType(raw.get("sale_type", "lien")),
            source_type=SourceType.STATE_AGENCY,
            source_url=_URL,
            confidence_score=0.85,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/state_agencies/test_colorado.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/tdc_auction_calendar/collectors/state_agencies/ tests/collectors/ tests/fixtures/state_agencies/
git commit -m "feat(collectors): add Colorado state agency collector with CCTPTA source (issue #11)"
```

---

## Chunk 3: Remaining three collectors

### Task 6: California collector

**Files:**
- Create: `src/tdc_auction_calendar/collectors/state_agencies/california.py`
- Create: `tests/fixtures/state_agencies/california_sco.json`
- Create: `tests/collectors/state_agencies/test_california.py`
- Modify: `src/tdc_auction_calendar/collectors/state_agencies/__init__.py`

- [ ] **Step 1: Create fixture data**

Create `tests/fixtures/state_agencies/california_sco.json` with realistic extracted data. California covers all 58 counties from one page. Include at least 15 representative counties:

```json
[
  {"county": "Alameda", "sale_date": "2026-10-15", "auction_type": "deed"},
  {"county": "Fresno", "sale_date": "2026-10-20", "auction_type": "deed"},
  {"county": "Kern", "sale_date": "2026-10-22", "auction_type": "deed"},
  {"county": "Los Angeles", "sale_date": "2026-10-25", "auction_type": "deed"},
  {"county": "Madera", "sale_date": "2026-10-18", "auction_type": "deed"},
  {"county": "Marin", "sale_date": "2026-10-20", "auction_type": "deed"},
  {"county": "Merced", "sale_date": "2026-10-22", "auction_type": "deed"},
  {"county": "Orange", "sale_date": "2026-10-25", "auction_type": "deed"},
  {"county": "Riverside", "sale_date": "2026-10-15", "auction_type": "deed"},
  {"county": "Sacramento", "sale_date": "2026-10-20", "auction_type": "deed"},
  {"county": "San Bernardino", "sale_date": "2026-10-22", "auction_type": "deed"},
  {"county": "San Diego", "sale_date": "2026-10-25", "auction_type": "deed"},
  {"county": "San Francisco", "sale_date": "2026-10-15", "auction_type": "deed"},
  {"county": "Santa Clara", "sale_date": "2026-10-20", "auction_type": "deed"},
  {"county": "Ventura", "sale_date": "2026-10-22", "auction_type": "deed"}
]
```

- [ ] **Step 2: Write failing tests**

Create `tests/collectors/state_agencies/test_california.py`. Follow the same pattern as `test_colorado.py` but with:
- `CaliforniaCollector` import from `tdc_auction_calendar.collectors.state_agencies.california`
- `collector.name == "california_state_agency"`
- `auction.state == "CA"`
- `sale_type == SaleType.DEED` (California is a deed state)
- `source_url == "https://sco.ca.gov/ardtax_public_auction.html"`
- Fixture loads from `california_sco.json`
- Happy path expects >= 10 records
- Tests: `test_name`, `test_source_type`, `test_normalize_valid_record`, `test_normalize_invalid_record_raises`, `test_fetch_returns_auctions`, `test_fetch_empty_data_returns_empty`, `test_fetch_skips_invalid_records`

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/state_agencies/test_california.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement CaliforniaCollector**

Create `src/tdc_auction_calendar/collectors/state_agencies/california.py` following the Colorado pattern:
- `_URL = "https://sco.ca.gov/ardtax_public_auction.html"`
- `_PROMPT = "Extract all county tax deed public auction dates from this page. Each row should have county name, sale date, and auction type."`
- Schema: `CaliforniaAuctionRecord` with `county: str`, `sale_date: str`, `auction_type: str = "deed"`
- `normalize()`: `state="CA"`, maps `auction_type` to `SaleType` (default "deed")

Update `src/tdc_auction_calendar/collectors/state_agencies/__init__.py` to export `CaliforniaCollector`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/state_agencies/test_california.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/state_agencies/california.py src/tdc_auction_calendar/collectors/state_agencies/__init__.py tests/collectors/state_agencies/test_california.py tests/fixtures/state_agencies/california_sco.json
git commit -m "feat(collectors): add California state agency collector with SCO source (issue #11)"
```

---

### Task 7: Arkansas collector

**Files:**
- Create: `src/tdc_auction_calendar/collectors/state_agencies/arkansas.py`
- Create: `tests/fixtures/state_agencies/arkansas_cosl.json`
- Create: `tests/collectors/state_agencies/test_arkansas.py`
- Modify: `src/tdc_auction_calendar/collectors/state_agencies/__init__.py`

- [ ] **Step 1: Create fixture data**

Create `tests/fixtures/state_agencies/arkansas_cosl.json` with representative AR county deed sale data (at least 10 counties):

```json
[
  {"county": "Benton", "sale_date": "2026-06-10", "sale_type": "deed"},
  {"county": "Craighead", "sale_date": "2026-06-15", "sale_type": "deed"},
  {"county": "Faulkner", "sale_date": "2026-06-12", "sale_type": "deed"},
  {"county": "Garland", "sale_date": "2026-06-18", "sale_type": "deed"},
  {"county": "Jefferson", "sale_date": "2026-06-10", "sale_type": "deed"},
  {"county": "Lonoke", "sale_date": "2026-06-15", "sale_type": "deed"},
  {"county": "Pope", "sale_date": "2026-06-12", "sale_type": "deed"},
  {"county": "Pulaski", "sale_date": "2026-06-10", "sale_type": "deed"},
  {"county": "Saline", "sale_date": "2026-06-18", "sale_type": "deed"},
  {"county": "Sebastian", "sale_date": "2026-06-15", "sale_type": "deed"},
  {"county": "Washington", "sale_date": "2026-06-12", "sale_type": "deed"},
  {"county": "White", "sale_date": "2026-06-18", "sale_type": "deed"}
]
```

- [ ] **Step 2: Write failing tests**

Create `tests/collectors/state_agencies/test_arkansas.py`. Same pattern as Colorado:
- `ArkansasCollector` from `tdc_auction_calendar.collectors.state_agencies.arkansas`
- `collector.name == "arkansas_state_agency"`
- `auction.state == "AR"`, `sale_type == SaleType.DEED`
- `source_url == "https://cosl.org"`
- Happy path expects >= 10 records

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/state_agencies/test_arkansas.py -v`
Expected: FAIL

- [ ] **Step 4: Implement ArkansasCollector**

Create `src/tdc_auction_calendar/collectors/state_agencies/arkansas.py`:
- `_URL = "https://cosl.org"`
- `_PROMPT = "Extract all county tax deed sale dates from this page. Each row should have county name, sale date, and sale type."`
- Schema: `ArkansasAuctionRecord` with `county: str`, `sale_date: str`, `sale_type: str = "deed"`
- `normalize()`: `state="AR"`, default `SaleType.DEED`

Update `__init__.py` to export `ArkansasCollector`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/state_agencies/test_arkansas.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/state_agencies/arkansas.py src/tdc_auction_calendar/collectors/state_agencies/__init__.py tests/collectors/state_agencies/test_arkansas.py tests/fixtures/state_agencies/arkansas_cosl.json
git commit -m "feat(collectors): add Arkansas state agency collector with COSL source (issue #11)"
```

---

### Task 8: Iowa collector

**Files:**
- Create: `src/tdc_auction_calendar/collectors/state_agencies/iowa.py`
- Create: `tests/fixtures/state_agencies/iowa_treasurers.json`
- Create: `tests/collectors/state_agencies/test_iowa.py`
- Modify: `src/tdc_auction_calendar/collectors/state_agencies/__init__.py`

- [ ] **Step 1: Create fixture data**

Create `tests/fixtures/state_agencies/iowa_treasurers.json` with representative IA county lien sale data (at least 10 counties):

```json
[
  {"county": "Black Hawk", "sale_date": "2026-06-15", "sale_type": "lien"},
  {"county": "Dallas", "sale_date": "2026-06-16", "sale_type": "lien"},
  {"county": "Dubuque", "sale_date": "2026-06-15", "sale_type": "lien"},
  {"county": "Johnson", "sale_date": "2026-06-17", "sale_type": "lien"},
  {"county": "Linn", "sale_date": "2026-06-15", "sale_type": "lien"},
  {"county": "Polk", "sale_date": "2026-06-16", "sale_type": "lien"},
  {"county": "Pottawattamie", "sale_date": "2026-06-17", "sale_type": "lien"},
  {"county": "Scott", "sale_date": "2026-06-15", "sale_type": "lien"},
  {"county": "Story", "sale_date": "2026-06-16", "sale_type": "lien"},
  {"county": "Woodbury", "sale_date": "2026-06-17", "sale_type": "lien"},
  {"county": "Warren", "sale_date": "2026-06-15", "sale_type": "lien"}
]
```

- [ ] **Step 2: Write failing tests**

Create `tests/collectors/state_agencies/test_iowa.py`. Same pattern:
- `IowaCollector` from `tdc_auction_calendar.collectors.state_agencies.iowa`
- `collector.name == "iowa_state_agency"`
- `auction.state == "IA"`, `sale_type == SaleType.LIEN`
- `source_url == "https://iowatreasurers.org"`
- Happy path expects >= 10 records

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/state_agencies/test_iowa.py -v`
Expected: FAIL

- [ ] **Step 4: Implement IowaCollector**

Create `src/tdc_auction_calendar/collectors/state_agencies/iowa.py`:
- `_URL = "https://iowatreasurers.org"`
- `_PROMPT = "Extract all county tax lien sale dates from this page. Each row should have county name, sale date, and sale type."`
- Schema: `IowaAuctionRecord` with `county: str`, `sale_date: str`, `sale_type: str = "lien"`
- `normalize()`: `state="IA"`, default `SaleType.LIEN`

Update `__init__.py` to export `IowaCollector`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/state_agencies/test_iowa.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/state_agencies/iowa.py src/tdc_auction_calendar/collectors/state_agencies/__init__.py tests/collectors/state_agencies/test_iowa.py tests/fixtures/state_agencies/iowa_treasurers.json
git commit -m "feat(collectors): add Iowa state agency collector with IowaTreasurers source (issue #11)"
```

---

## Chunk 4: Wire up exports and final verification

### Task 9: Update top-level collectors exports

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/__init__.py`

- [ ] **Step 1: Update exports**

Change `src/tdc_auction_calendar/collectors/__init__.py` from:

```python
from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.statutory import StatutoryCollector

__all__ = ["BaseCollector", "StatutoryCollector"]
```

to:

```python
from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.state_agencies import (
    ArkansasCollector,
    CaliforniaCollector,
    ColoradoCollector,
    IowaCollector,
)
from tdc_auction_calendar.collectors.statutory import StatutoryCollector

__all__ = [
    "ArkansasCollector",
    "BaseCollector",
    "CaliforniaCollector",
    "ColoradoCollector",
    "IowaCollector",
    "StatutoryCollector",
]
```

- [ ] **Step 2: Verify imports work**

Run: `uv run python -c "from tdc_auction_calendar.collectors import ColoradoCollector, CaliforniaCollector, ArkansasCollector, IowaCollector; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS, zero regressions

- [ ] **Step 4: Commit**

```bash
git add src/tdc_auction_calendar/collectors/__init__.py
git commit -m "feat(collectors): wire up state agency collector exports (issue #11)"
```

### Task 10: Final verification

- [ ] **Step 1: Run full test suite with verbose output**

Run: `uv run pytest -v --tb=short`
Expected: ALL PASS

- [ ] **Step 2: Verify acceptance criteria**

Check each acceptance criterion from issue #11:
- Each collector extends BaseCollector: verify in code
- Each tested with recorded fixtures (no live HTTP): verify no network calls in tests
- Handles format changes gracefully: verify `test_fetch_skips_invalid_records` passes for each
- CO returns >= 30 county records: verify `test_fetch_returns_auctions` asserts `>= 30`

- [ ] **Step 3: Count tests**

Run: `uv run pytest --co -q | tail -1`
Record total test count for PR description.
