# Scraping Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared scraping client that downstream collectors (#11–13) use to fetch and extract data from auction websites.

**Architecture:** Abstract `PageFetcher` protocol with Cloudflare (primary) and Crawl4AI (fallback) backends, wrapped by `ScrapeClient` which adds rate limiting, caching, retries, and extraction. Collectors call `scrape(url, schema=MySchema)` and get structured data back.

**Tech Stack:** httpx (Cloudflare API), crawl4ai (local browser), anthropic SDK (LLM extraction), pydantic (schemas), structlog (logging)

**Spec:** `docs/superpowers/specs/2026-03-11-crawl4ai-scraping-infra-design.md`

---

## File Structure

```
src/tdc_auction_calendar/collectors/scraping/
├── __init__.py              # re-exports public API
├── client.py                # ScrapeClient, ScrapeResult, ScrapeError, create_scrape_client
├── rate_limiter.py          # RateLimiter
├── cache.py                 # ResponseCache
├── extraction.py            # ExtractionStrategy protocol, LLMExtraction, CSSExtraction
├── fetchers/
│   ├── __init__.py
│   ├── protocol.py          # PageFetcher protocol, FetchResult model
│   ├── cloudflare.py        # CloudflareFetcher
│   └── crawl4ai.py          # Crawl4AiFetcher

tests/
├── scraping/
│   ├── __init__.py
│   ├── conftest.py          # shared fixtures (sample FetchResult, etc.)
│   ├── test_protocol.py     # FetchResult model tests
│   ├── test_rate_limiter.py # RateLimiter tests
│   ├── test_cache.py        # ResponseCache tests
│   ├── test_cloudflare.py   # CloudflareFetcher tests
│   ├── test_crawl4ai.py     # Crawl4AiFetcher tests
│   ├── test_extraction.py   # LLM + CSS extraction tests
│   └── test_client.py       # ScrapeClient integration tests
```

---

## Chunk 1: Foundation — Protocol, Models, Rate Limiter, Cache

### Task 1: FetchResult model + PageFetcher protocol

**Files:**
- Create: `src/tdc_auction_calendar/collectors/scraping/__init__.py`
- Create: `src/tdc_auction_calendar/collectors/scraping/fetchers/__init__.py`
- Create: `src/tdc_auction_calendar/collectors/scraping/fetchers/protocol.py`
- Create: `tests/scraping/__init__.py`
- Create: `tests/scraping/test_protocol.py`

- [ ] **Step 1: Write FetchResult tests**

```python
# tests/scraping/test_protocol.py
"""Tests for FetchResult model."""

from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult


def test_fetch_result_minimal():
    """FetchResult can be created with required fields only."""
    result = FetchResult(url="https://example.com", status_code=200, fetcher="cloudflare")
    assert result.url == "https://example.com"
    assert result.status_code == 200
    assert result.fetcher == "cloudflare"
    assert result.html is None
    assert result.markdown is None


def test_fetch_result_with_content():
    """FetchResult stores html and markdown content."""
    result = FetchResult(
        url="https://example.com",
        status_code=200,
        fetcher="crawl4ai",
        html="<h1>Auction</h1>",
        markdown="# Auction",
    )
    assert result.html == "<h1>Auction</h1>"
    assert result.markdown == "# Auction"


def test_fetch_result_serializes_to_dict():
    """FetchResult can be serialized for caching."""
    result = FetchResult(url="https://example.com", status_code=200, fetcher="cloudflare")
    data = result.model_dump()
    assert data["url"] == "https://example.com"
    restored = FetchResult.model_validate(data)
    assert restored == result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create protocol module**

```python
# src/tdc_auction_calendar/collectors/scraping/fetchers/protocol.py
"""PageFetcher protocol and FetchResult model."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class FetchResult(BaseModel):
    """Result of fetching a single URL."""

    url: str
    html: str | None = None
    markdown: str | None = None
    status_code: int
    fetcher: str  # "cloudflare" or "crawl4ai"


class PageFetcher(Protocol):
    """Protocol for page-fetching backends."""

    async def fetch(self, url: str, *, render_js: bool = True) -> FetchResult: ...
```

Also create the `__init__.py` files and shared test fixtures:

```python
# src/tdc_auction_calendar/collectors/scraping/__init__.py
"""Shared scraping infrastructure."""

# src/tdc_auction_calendar/collectors/scraping/fetchers/__init__.py
"""Fetcher backends."""

# tests/scraping/__init__.py
```

```python
# tests/scraping/conftest.py
"""Shared fixtures for scraping tests."""

import pytest

from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult


@pytest.fixture()
def sample_fetch_result():
    """A valid FetchResult for test reuse."""
    return FetchResult(
        url="https://example.com/auctions",
        status_code=200,
        fetcher="cloudflare",
        html="<h1>Auctions</h1>",
        markdown="# Auctions",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_protocol.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/ tests/scraping/
git commit -m "feat(scraping): add FetchResult model and PageFetcher protocol (issue #10)"
```

---

### Task 2: RateLimiter

**Files:**
- Create: `src/tdc_auction_calendar/collectors/scraping/rate_limiter.py`
- Create: `tests/scraping/test_rate_limiter.py`

- [ ] **Step 1: Write RateLimiter tests**

```python
# tests/scraping/test_rate_limiter.py
"""Tests for per-domain rate limiter."""

import asyncio
from unittest.mock import AsyncMock, patch

from tdc_auction_calendar.collectors.scraping.rate_limiter import RateLimiter


async def test_first_request_no_delay():
    """First request to a domain should not wait."""
    limiter = RateLimiter(default_delay=2.0)
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait("example.com")
        mock_sleep.assert_not_called()


async def test_second_request_waits():
    """Second request to same domain should wait for the delay."""
    limiter = RateLimiter(default_delay=1.0)
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait("example.com")
        # Simulate time passing by setting last_request to now
        await limiter.wait("example.com")
        mock_sleep.assert_called_once()
        delay = mock_sleep.call_args[0][0]
        assert 0.0 < delay <= 1.0


async def test_different_domains_independent():
    """Requests to different domains should not block each other."""
    limiter = RateLimiter(default_delay=2.0)
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait("example.com")
        await limiter.wait("other.com")
        mock_sleep.assert_not_called()


async def test_per_domain_override():
    """Per-domain delay overrides the default."""
    limiter = RateLimiter(default_delay=1.0, per_domain={"slow.com": 5.0})
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait("slow.com")
        await limiter.wait("slow.com")
        delay = mock_sleep.call_args[0][0]
        assert delay > 1.0  # uses 5.0s override, not 1.0s default
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_rate_limiter.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement RateLimiter**

```python
# src/tdc_auction_calendar/collectors/scraping/rate_limiter.py
"""Per-domain rate limiter for scraping requests."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Enforces a minimum delay between requests to the same domain."""

    def __init__(
        self,
        default_delay: float = 2.0,
        per_domain: dict[str, float] | None = None,
    ) -> None:
        self._default_delay = default_delay
        self._per_domain = per_domain or {}
        self._last_request: dict[str, float] = {}

    async def wait(self, domain: str) -> None:
        """Wait until the per-domain delay has elapsed since the last request."""
        delay = self._per_domain.get(domain, self._default_delay)
        last = self._last_request.get(domain)

        if last is not None:
            elapsed = time.monotonic() - last
            remaining = delay - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)

        self._last_request[domain] = time.monotonic()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_rate_limiter.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/rate_limiter.py tests/scraping/test_rate_limiter.py
git commit -m "feat(scraping): add per-domain rate limiter (issue #10)"
```

---

### Task 3: ResponseCache

**Files:**
- Create: `src/tdc_auction_calendar/collectors/scraping/cache.py`
- Create: `tests/scraping/test_cache.py`

- [ ] **Step 1: Write ResponseCache tests**

```python
# tests/scraping/test_cache.py
"""Tests for file-based response cache."""

import json
import time

import pytest

from tdc_auction_calendar.collectors.scraping.cache import ResponseCache
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult


@pytest.fixture()
def cache(tmp_path):
    """ResponseCache using a temporary directory."""
    return ResponseCache(cache_dir=str(tmp_path), ttl=3600)


@pytest.fixture()
def sample_result():
    return FetchResult(
        url="https://example.com/auctions",
        status_code=200,
        fetcher="cloudflare",
        html="<h1>Auctions</h1>",
        markdown="# Auctions",
    )


async def test_cache_miss_returns_none(cache):
    """get() returns None for uncached URLs."""
    result = await cache.get("https://example.com", render_js=True)
    assert result is None


async def test_cache_put_then_get(cache, sample_result):
    """Cached result is returned on subsequent get()."""
    await cache.put("https://example.com", render_js=True, result=sample_result)
    cached = await cache.get("https://example.com", render_js=True)
    assert cached is not None
    assert cached.url == sample_result.url
    assert cached.html == sample_result.html


async def test_cache_different_render_js(cache, sample_result):
    """Different render_js values produce different cache keys."""
    await cache.put("https://example.com", render_js=True, result=sample_result)
    cached = await cache.get("https://example.com", render_js=False)
    assert cached is None


async def test_cache_expired_returns_none(tmp_path, sample_result):
    """Expired entries return None."""
    cache = ResponseCache(cache_dir=str(tmp_path), ttl=0)  # immediate expiry
    await cache.put("https://example.com", render_js=True, result=sample_result)
    # TTL=0 means already expired
    cached = await cache.get("https://example.com", render_js=True)
    assert cached is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement ResponseCache**

```python
# src/tdc_auction_calendar/collectors/scraping/cache.py
"""File-based response cache for scraping results."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import structlog

from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

logger = structlog.get_logger()


class ResponseCache:
    """File-based cache for FetchResult objects."""

    def __init__(self, cache_dir: str = "data/cache", ttl: int = 21600) -> None:
        self._cache_dir = Path(cache_dir)
        self._ttl = ttl
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, url: str, render_js: bool) -> str:
        raw = f"{url}:{render_js}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    async def get(self, url: str, render_js: bool) -> FetchResult | None:
        """Return cached FetchResult if present and not expired, else None."""
        key = self._cache_key(url, render_js)
        path = self._cache_path(key)

        if not path.exists():
            logger.debug("cache_miss", url=url, reason="not_found")
            return None

        data = json.loads(path.read_text())
        if time.time() > data["expires_at"]:
            logger.debug("cache_miss", url=url, reason="expired")
            path.unlink()
            return None

        logger.debug("cache_hit", url=url)
        return FetchResult.model_validate(data["result"])

    async def put(self, url: str, render_js: bool, result: FetchResult) -> None:
        """Write FetchResult to cache with expiry metadata."""
        key = self._cache_key(url, render_js)
        path = self._cache_path(key)

        data = {
            "expires_at": time.time() + self._ttl,
            "result": result.model_dump(),
        }
        path.write_text(json.dumps(data))
        logger.debug("cache_write", url=url, ttl=self._ttl)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_cache.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/cache.py tests/scraping/test_cache.py
git commit -m "feat(scraping): add file-based response cache (issue #10)"
```

---

## Chunk 2: Fetcher Backends

### Task 4: CloudflareFetcher

**Files:**
- Create: `src/tdc_auction_calendar/collectors/scraping/fetchers/cloudflare.py`
- Create: `tests/scraping/test_cloudflare.py`

- [ ] **Step 1: Write CloudflareFetcher tests**

```python
# tests/scraping/test_cloudflare.py
"""Tests for CloudflareFetcher with mocked Cloudflare API."""

import httpx
import pytest
from unittest.mock import patch, AsyncMock

from tdc_auction_calendar.collectors.scraping.fetchers.cloudflare import CloudflareFetcher


@pytest.fixture()
def fetcher():
    """CloudflareFetcher with test credentials."""
    return CloudflareFetcher(account_id="test-account", api_token="test-token")


def _mock_post_response(job_id="job-123"):
    """Mock response for POST /crawl (job creation)."""
    return httpx.Response(200, json={"id": job_id})


def _mock_poll_running():
    """Mock response for GET /crawl/<id> — still running."""
    return httpx.Response(200, json={"status": "running", "result": []})


def _mock_poll_completed(url="https://example.com"):
    """Mock response for GET /crawl/<id> — completed."""
    return httpx.Response(200, json={
        "status": "completed",
        "result": [{
            "url": url,
            "status": "completed",
            "html": "<h1>Auction Sale</h1>",
            "markdown": "# Auction Sale",
            "metadata": {"statusCode": 200},
        }],
    })


def _mock_poll_errored():
    """Mock response for GET /crawl/<id> — errored."""
    return httpx.Response(200, json={"status": "errored", "result": []})


async def test_fetch_success(fetcher):
    """Successful fetch: POST creates job, poll returns completed result."""
    responses = [_mock_post_response(), _mock_poll_completed()]
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = responses[0]
        mock_http.get.return_value = responses[1]

        result = await fetcher.fetch("https://example.com")

    assert result.status_code == 200
    assert result.fetcher == "cloudflare"
    assert result.html == "<h1>Auction Sale</h1>"
    assert result.markdown == "# Auction Sale"


async def test_fetch_polls_until_complete(fetcher):
    """Fetcher polls multiple times before getting completed status."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.side_effect = [_mock_poll_running(), _mock_poll_running(), _mock_poll_completed()]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await fetcher.fetch("https://example.com")

    assert result.status_code == 200
    assert mock_http.get.call_count == 3


async def test_fetch_errored_job_raises(fetcher):
    """Errored job raises an exception."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = _mock_poll_errored()

        with pytest.raises(Exception, match="failed"):
            await fetcher.fetch("https://example.com")


async def test_fetch_no_render(fetcher):
    """render_js=False passes render=False to Cloudflare API."""
    with patch.object(fetcher, "_http", new_callable=AsyncMock) as mock_http:
        mock_http.post.return_value = _mock_post_response()
        mock_http.get.return_value = _mock_poll_completed()

        await fetcher.fetch("https://example.com", render_js=False)

    call_kwargs = mock_http.post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert body["render"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_cloudflare.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CloudflareFetcher**

```python
# src/tdc_auction_calendar/collectors/scraping/fetchers/cloudflare.py
"""Cloudflare Browser Rendering fetcher backend."""

from __future__ import annotations

import asyncio
import os

import httpx
import structlog

from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

logger = structlog.get_logger()

_BASE_URL = "https://api.cloudflare.com/client/v4/accounts"
_POLL_INTERVAL = 2.0
_POLL_TIMEOUT = 90.0


class CloudflareFetchError(Exception):
    """Raised when a Cloudflare crawl job fails."""


class CloudflareFetcher:
    """Fetches pages via Cloudflare Browser Rendering /crawl API."""

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
        connect_timeout: float = 30.0,
        read_timeout: float = 60.0,
    ) -> None:
        self._account_id = account_id or os.environ["CLOUDFLARE_ACCOUNT_ID"]
        self._api_token = api_token or os.environ["CLOUDFLARE_API_TOKEN"]
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=connect_timeout, read=read_timeout, write=30.0, pool=30.0),
            headers={"Authorization": f"Bearer {self._api_token}"},
        )

    @property
    def _crawl_url(self) -> str:
        return f"{_BASE_URL}/{self._account_id}/browser-rendering/crawl"

    async def fetch(self, url: str, *, render_js: bool = True) -> FetchResult:
        """Submit a crawl job and poll until complete."""
        logger.info("cloudflare_fetch_start", url=url, render_js=render_js)

        # POST to create job
        resp = await self._http.post(
            self._crawl_url,
            json={
                "url": url,
                "formats": ["markdown", "html"],
                "render": render_js,
                "limit": 1,
            },
        )
        resp.raise_for_status()
        job_id = resp.json()["id"]

        # Poll for completion
        elapsed = 0.0
        while elapsed < _POLL_TIMEOUT:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

            poll_resp = await self._http.get(f"{self._crawl_url}/{job_id}")
            poll_resp.raise_for_status()
            data = poll_resp.json()
            status = data["status"]

            if status == "running":
                continue
            if status == "completed":
                page = data["result"][0]
                status_code = page.get("metadata", {}).get("statusCode", 200)
                return FetchResult(
                    url=url,
                    html=page.get("html"),
                    markdown=page.get("markdown"),
                    status_code=status_code,
                    fetcher="cloudflare",
                )

            # errored, cancelled_*, etc.
            raise CloudflareFetchError(
                f"Cloudflare crawl job {job_id} failed with status: {status}"
            )

        raise CloudflareFetchError(
            f"Cloudflare crawl job {job_id} timed out after {_POLL_TIMEOUT}s"
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_cloudflare.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/fetchers/cloudflare.py tests/scraping/test_cloudflare.py
git commit -m "feat(scraping): add CloudflareFetcher backend (issue #10)"
```

---

### Task 5: Crawl4AiFetcher

**Files:**
- Create: `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py`
- Create: `tests/scraping/test_crawl4ai.py`

- [ ] **Step 1: Write Crawl4AiFetcher tests**

```python
# tests/scraping/test_crawl4ai.py
"""Tests for Crawl4AiFetcher with mocked AsyncWebCrawler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import Crawl4AiFetcher


def _mock_crawl_result(html="<h1>Sale</h1>", markdown="# Sale", status_code=200):
    """Create a mock CrawlResult."""
    result = MagicMock()
    result.html = html
    result.markdown = markdown
    result.status_code = status_code
    result.success = status_code == 200
    return result


async def test_fetch_success():
    """Successful fetch returns HTML and markdown from crawler."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result()

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    result = await fetcher.fetch("https://example.com")

    assert result.status_code == 200
    assert result.fetcher == "crawl4ai"
    assert result.html == "<h1>Sale</h1>"
    assert result.markdown == "# Sale"


async def test_fetch_passes_url_to_crawler():
    """The URL is forwarded to the crawler."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result()

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    await fetcher.fetch("https://county.gov/auction")

    mock_crawler.arun.assert_called_once()
    call_args = mock_crawler.arun.call_args
    assert call_args[0][0] == "https://county.gov/auction" or call_args.kwargs.get("url") == "https://county.gov/auction"


async def test_fetch_error_propagates():
    """Crawler errors propagate as exceptions."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = RuntimeError("Browser crashed")

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    with pytest.raises(RuntimeError, match="Browser crashed"):
        await fetcher.fetch("https://example.com")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_crawl4ai.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement Crawl4AiFetcher**

```python
# src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py
"""Crawl4AI fetcher backend using local headless browser."""

from __future__ import annotations

from typing import Any

import structlog

from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

logger = structlog.get_logger()


class Crawl4AiFetcher:
    """Fetches pages via Crawl4AI's AsyncWebCrawler."""

    def __init__(self, crawler: Any = None) -> None:
        self._crawler = crawler
        self._owns_crawler = crawler is None

    async def _get_crawler(self) -> Any:
        if self._crawler is None:
            from crawl4ai import AsyncWebCrawler

            self._crawler = AsyncWebCrawler()
            await self._crawler.__aenter__()
        return self._crawler

    async def fetch(self, url: str, *, render_js: bool = True) -> FetchResult:
        """Fetch a page using the local headless browser."""
        logger.info("crawl4ai_fetch_start", url=url, render_js=render_js)

        crawler = await self._get_crawler()
        result = await crawler.arun(url)

        return FetchResult(
            url=url,
            html=result.html,
            markdown=result.markdown,
            status_code=result.status_code,
            fetcher="crawl4ai",
        )

    async def close(self) -> None:
        """Close the crawler if we own it."""
        if self._owns_crawler and self._crawler is not None:
            await self._crawler.__aexit__(None, None, None)
            self._crawler = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_crawl4ai.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py tests/scraping/test_crawl4ai.py
git commit -m "feat(scraping): add Crawl4AiFetcher backend (issue #10)"
```

---

## Chunk 3: Extraction Layer

### Task 6: LLMExtraction

**Files:**
- Create: `src/tdc_auction_calendar/collectors/scraping/extraction.py`
- Create: `tests/scraping/test_extraction.py`

- [ ] **Step 1: Write LLMExtraction tests**

```python
# tests/scraping/test_extraction.py
"""Tests for extraction strategies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from tdc_auction_calendar.collectors.scraping.extraction import (
    CSSExtraction,
    ExtractionStrategy,
    LLMExtraction,
)


# --- Test schema ---

class AuctionInfo(BaseModel):
    county: str
    date: str
    sale_type: str


# --- LLMExtraction tests ---


async def test_llm_extraction_returns_pydantic_model():
    """LLMExtraction returns a validated Pydantic instance."""
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[
            MagicMock(
                type="tool_use",
                input={"county": "Miami-Dade", "date": "2026-06-01", "sale_type": "deed"},
            )
        ]
    )

    extractor = LLMExtraction(client=mock_client)
    result = await extractor.extract("# Auction\nMiami-Dade deed sale June 1", schema=AuctionInfo)

    assert isinstance(result, AuctionInfo)
    assert result.county == "Miami-Dade"
    assert result.sale_type == "deed"


async def test_llm_extraction_sends_schema_as_tool():
    """LLMExtraction sends the Pydantic schema as a tool definition."""
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[
            MagicMock(
                type="tool_use",
                input={"county": "Harris", "date": "2026-07-01", "sale_type": "deed"},
            )
        ]
    )

    extractor = LLMExtraction(client=mock_client)
    await extractor.extract("some content", schema=AuctionInfo)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    tools = call_kwargs["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "AuctionInfo"


async def test_llm_extraction_requires_schema():
    """LLMExtraction raises ValueError if no schema provided."""
    extractor = LLMExtraction(client=AsyncMock())
    with pytest.raises(ValueError, match="schema"):
        await extractor.extract("content")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_extraction.py::test_llm_extraction_returns_pydantic_model tests/scraping/test_extraction.py::test_llm_extraction_sends_schema_as_tool tests/scraping/test_extraction.py::test_llm_extraction_requires_schema -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement extraction module with LLMExtraction**

```python
# src/tdc_auction_calendar/collectors/scraping/extraction.py
"""Extraction strategies for converting page content to structured data."""

from __future__ import annotations

import os
from typing import Any, Protocol

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class ExtractionStrategy(Protocol):
    """Protocol for content extraction strategies."""

    async def extract(
        self, content: str, *, schema: type[BaseModel] | None = None
    ) -> BaseModel | dict | list[dict]: ...


class LLMExtraction:
    """Extracts structured data using Claude's tool_use feature."""

    def __init__(
        self,
        client: Any = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._client = client
        self._model = model

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def extract(
        self, content: str, *, schema: type[BaseModel] | None = None
    ) -> BaseModel:
        """Extract structured data from content using a Pydantic schema.

        Sends the content to Claude with the schema as a tool definition,
        then validates the response against the schema.
        """
        if schema is None:
            raise ValueError("LLMExtraction requires a schema parameter")

        client = self._get_client()
        json_schema = schema.model_json_schema()

        # Remove keys that aren't valid in Claude tool input_schema
        json_schema.pop("title", None)

        tool = {
            "name": schema.__name__,
            "description": f"Extract {schema.__name__} data from the page content.",
            "input_schema": json_schema,
        }

        logger.info("llm_extraction_start", schema=schema.__name__, model=self._model)

        response = await client.messages.create(
            model=self._model,
            max_tokens=1024,
            tools=[tool],
            tool_choice={"type": "tool", "name": schema.__name__},
            messages=[
                {
                    "role": "user",
                    "content": f"Extract structured data from this page content:\n\n{content}",
                }
            ],
        )

        # Find the tool_use block in the response
        for block in response.content:
            if block.type == "tool_use":
                logger.info("llm_extraction_complete", schema=schema.__name__)
                return schema.model_validate(block.input)

        raise RuntimeError(f"No tool_use block in Claude response for {schema.__name__}")
```

- [ ] **Step 4: Run LLM extraction tests to verify they pass**

Run: `uv run pytest tests/scraping/test_extraction.py::test_llm_extraction_returns_pydantic_model tests/scraping/test_extraction.py::test_llm_extraction_sends_schema_as_tool tests/scraping/test_extraction.py::test_llm_extraction_requires_schema -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/extraction.py tests/scraping/test_extraction.py
git commit -m "feat(scraping): add LLMExtraction strategy with Claude tool_use (issue #10)"
```

---

### Task 7: CSSExtraction

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/extraction.py`
- Modify: `tests/scraping/test_extraction.py`

- [ ] **Step 1: Add CSSExtraction tests to test_extraction.py**

Append to `tests/scraping/test_extraction.py`:

```python
# --- CSSExtraction tests ---

SAMPLE_HTML = """
<table>
  <tr><td class="county">Miami-Dade</td><td class="date">2026-06-01</td></tr>
  <tr><td class="county">Broward</td><td class="date">2026-07-15</td></tr>
</table>
"""


async def test_css_extraction_returns_list_of_dicts():
    """CSSExtraction extracts data using CSS selectors."""
    extractor = CSSExtraction(
        selectors={"county": "td.county", "date": "td.date"},
        row_selector="tr",
    )
    result = await extractor.extract(SAMPLE_HTML)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["county"] == "Miami-Dade"
    assert result[1]["date"] == "2026-07-15"


async def test_css_extraction_empty_table():
    """CSSExtraction returns empty list when no rows match."""
    extractor = CSSExtraction(
        selectors={"county": "td.county"},
        row_selector="tr.auction-row",
    )
    result = await extractor.extract("<table></table>")
    assert result == []


async def test_css_extraction_ignores_schema():
    """CSSExtraction works regardless of schema parameter."""
    extractor = CSSExtraction(
        selectors={"county": "td.county"},
        row_selector="tr",
    )
    result = await extractor.extract(SAMPLE_HTML, schema=AuctionInfo)
    assert isinstance(result, list)
```

- [ ] **Step 2: Run CSS tests to verify they fail**

Run: `uv run pytest tests/scraping/test_extraction.py::test_css_extraction_returns_list_of_dicts -v`
Expected: FAIL — `CSSExtraction` not implemented yet

- [ ] **Step 3: Implement CSSExtraction**

Add to `src/tdc_auction_calendar/collectors/scraping/extraction.py`:

```python
from html.parser import HTMLParser
import re


class _SimpleHTMLExtractor(HTMLParser):
    """Minimal HTML parser that extracts text by CSS class selector."""

    def __init__(self) -> None:
        super().__init__()
        self._elements: list[dict[str, str]] = []
        self._current_tag: str | None = None
        self._current_classes: list[str] = []
        self._current_text: str = ""
        self._capture = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        classes = attr_dict.get("class", "").split()
        self._current_tag = tag
        self._current_classes = classes
        self._capture = True
        self._current_text = ""

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._current_text += data

    def handle_endtag(self, tag: str) -> None:
        if self._capture and tag == self._current_tag:
            self._elements.append({
                "tag": tag,
                "classes": self._current_classes,
                "text": self._current_text.strip(),
            })
            self._capture = False

    def get_elements(self) -> list[dict]:
        return self._elements


class CSSExtraction:
    """Extracts data from HTML using simple CSS class selectors.

    Supports selectors in the form 'tag.class' (e.g., 'td.county').
    """

    def __init__(
        self,
        selectors: dict[str, str],
        row_selector: str,
    ) -> None:
        self._selectors = selectors  # field_name -> "tag.class"
        self._row_selector = row_selector  # e.g., "tr"

    def _parse_selector(self, selector: str) -> tuple[str, str | None]:
        """Parse 'tag.class' into (tag, class) or (tag, None)."""
        if "." in selector:
            tag, cls = selector.split(".", 1)
            return tag, cls
        return selector, None

    async def extract(
        self, content: str, *, schema: type[BaseModel] | None = None
    ) -> list[dict]:
        """Extract rows of data from HTML content."""
        parser = _SimpleHTMLExtractor()
        parser.feed(content)
        elements = parser.get_elements()

        row_tag, row_class = self._parse_selector(self._row_selector)

        # Group elements by their position relative to row markers
        rows: list[dict[str, str]] = []
        current_row: dict[str, str] = {}

        for elem in elements:
            if elem["tag"] == row_tag and (row_class is None or row_class in elem["classes"]):
                if current_row:
                    rows.append(current_row)
                current_row = {}
                continue

            for field_name, selector in self._selectors.items():
                sel_tag, sel_class = self._parse_selector(selector)
                if elem["tag"] == sel_tag and (sel_class is None or sel_class in elem["classes"]):
                    current_row[field_name] = elem["text"]

        if current_row:
            rows.append(current_row)

        logger.info("css_extraction_complete", rows=len(rows))
        return rows
```

- [ ] **Step 4: Run all extraction tests to verify they pass**

Run: `uv run pytest tests/scraping/test_extraction.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/extraction.py tests/scraping/test_extraction.py
git commit -m "feat(scraping): add CSSExtraction strategy (issue #10)"
```

---

## Chunk 4: ScrapeClient — The Main Interface

### Task 8: ScrapeClient with retry, fallback, and orchestration

**Files:**
- Create: `src/tdc_auction_calendar/collectors/scraping/client.py`
- Create: `tests/scraping/test_client.py`

- [ ] **Step 1: Write ScrapeError and ScrapeResult tests**

```python
# tests/scraping/test_client.py
"""Tests for ScrapeClient orchestration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from tdc_auction_calendar.collectors.scraping.cache import ResponseCache
from tdc_auction_calendar.collectors.scraping.client import (
    ScrapeClient,
    ScrapeError,
    ScrapeResult,
)
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.collectors.scraping.rate_limiter import RateLimiter


# --- Fixtures ---


def _ok_result(url="https://example.com") -> FetchResult:
    return FetchResult(
        url=url, status_code=200, fetcher="primary",
        html="<h1>Sale</h1>", markdown="# Sale",
    )


@pytest.fixture()
def ok_fetcher():
    """A fetcher that always succeeds."""
    fetcher = AsyncMock()
    fetcher.fetch.return_value = _ok_result()
    fetcher.close = AsyncMock()
    return fetcher


@pytest.fixture()
def failing_fetcher():
    """A fetcher that always raises."""
    fetcher = AsyncMock()
    fetcher.fetch.side_effect = ConnectionError("down")
    fetcher.close = AsyncMock()
    return fetcher


@pytest.fixture()
def rate_limiter():
    return RateLimiter(default_delay=0.0)


@pytest.fixture()
def cache(tmp_path):
    return ResponseCache(cache_dir=str(tmp_path), ttl=3600)


def _make_client(primary, fallback=None, rate_limiter=None, cache=None):
    return ScrapeClient(
        primary=primary,
        fallback=fallback,
        rate_limiter=rate_limiter or RateLimiter(default_delay=0.0),
        cache=cache or MagicMock(),
    )


# --- Tests ---


async def test_scrape_success(ok_fetcher, rate_limiter, cache):
    """Basic scrape returns ScrapeResult with fetch data."""
    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)
    result = await client.scrape("https://example.com")

    assert isinstance(result, ScrapeResult)
    assert result.fetch.status_code == 200
    assert result.from_cache is False


async def test_scrape_uses_cache(ok_fetcher, rate_limiter, cache):
    """Second scrape of same URL returns cached result."""
    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)
    await client.scrape("https://example.com")
    result2 = await client.scrape("https://example.com")

    assert result2.from_cache is True
    # Fetcher called only once (second was cache hit)
    assert ok_fetcher.fetch.call_count == 1


async def test_scrape_fallback_on_primary_failure(failing_fetcher, ok_fetcher, rate_limiter, cache):
    """When primary fails, fallback is tried."""
    ok_fetcher.fetch.return_value = FetchResult(
        url="https://example.com", status_code=200, fetcher="fallback",
        html="<h1>Sale</h1>", markdown="# Sale",
    )
    client = _make_client(failing_fetcher, fallback=ok_fetcher, rate_limiter=rate_limiter, cache=cache)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await client.scrape("https://example.com")

    assert result.fetch.fetcher == "fallback"


async def test_scrape_all_fail_raises_scrape_error(failing_fetcher, rate_limiter, cache):
    """When all fetchers fail, ScrapeError is raised."""
    client = _make_client(failing_fetcher, rate_limiter=rate_limiter, cache=cache)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ScrapeError) as exc_info:
            await client.scrape("https://example.com")

    assert exc_info.value.url == "https://example.com"
    assert len(exc_info.value.attempts) > 0


async def test_scrape_retries_transient_errors(rate_limiter, cache):
    """Transient errors trigger retries before giving up."""
    fetcher = AsyncMock()
    fetcher.fetch.side_effect = [ConnectionError("timeout"), ConnectionError("timeout"), _ok_result()]
    fetcher.close = AsyncMock()

    client = _make_client(fetcher, rate_limiter=rate_limiter, cache=cache)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await client.scrape("https://example.com")

    assert result.fetch.status_code == 200
    assert fetcher.fetch.call_count == 3


async def test_scrape_no_retry_on_permanent_error(rate_limiter, cache):
    """4xx errors (PermanentFetchError) fail immediately without retries."""
    from tdc_auction_calendar.collectors.scraping.client import PermanentFetchError

    fetcher = AsyncMock()
    fetcher.fetch.side_effect = PermanentFetchError(404, "Not Found")
    fetcher.close = AsyncMock()

    client = _make_client(fetcher, rate_limiter=rate_limiter, cache=cache)

    with pytest.raises(ScrapeError) as exc_info:
        await client.scrape("https://example.com")

    # Should only attempt once — no retries for permanent errors
    assert fetcher.fetch.call_count == 1
    assert len(exc_info.value.attempts) == 1


async def test_scrape_context_manager(ok_fetcher, rate_limiter, cache):
    """ScrapeClient works as async context manager and calls close."""
    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)

    async with client as ctx:
        result = await ctx.scrape("https://example.com")
        assert result.fetch.status_code == 200

    ok_fetcher.close.assert_called_once()


async def test_scrape_with_extraction(ok_fetcher, rate_limiter, cache):
    """Extraction strategy is called on fetched content."""
    extractor = AsyncMock()
    extractor.extract.return_value = {"county": "Miami-Dade"}

    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)
    result = await client.scrape("https://example.com", extraction=extractor)

    extractor.extract.assert_called_once()
    assert result.data == {"county": "Miami-Dade"}


async def test_scrape_schema_without_extraction_defaults_to_llm(ok_fetcher, rate_limiter, cache):
    """Passing schema without extraction creates a default LLMExtraction."""

    class MySchema(BaseModel):
        county: str

    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)

    with patch(
        "tdc_auction_calendar.collectors.scraping.client.LLMExtraction"
    ) as MockLLM:
        mock_instance = AsyncMock()
        mock_instance.extract.return_value = MySchema(county="Test")
        MockLLM.return_value = mock_instance

        result = await client.scrape("https://example.com", schema=MySchema)

    assert result.data.county == "Test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement ScrapeClient** (includes `PermanentFetchError`)


```python
# src/tdc_auction_calendar/collectors/scraping/client.py
"""ScrapeClient — main interface for collectors to fetch and extract web data."""

from __future__ import annotations

import asyncio
import os
import random
from types import TracebackType
from typing import Any
from urllib.parse import urlparse

import structlog
from pydantic import BaseModel

from tdc_auction_calendar.collectors.scraping.cache import ResponseCache
from tdc_auction_calendar.collectors.scraping.extraction import LLMExtraction
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import (
    FetchResult,
    PageFetcher,
)
from tdc_auction_calendar.collectors.scraping.rate_limiter import RateLimiter

logger = structlog.get_logger()


class PermanentFetchError(Exception):
    """Raised for non-retryable errors (e.g., 4xx responses)."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"Permanent error {status_code}: {message}")


class ScrapeError(Exception):
    """Raised when all fetchers fail after retries."""

    def __init__(self, url: str, attempts: list[dict]) -> None:
        self.url = url
        self.attempts = attempts
        super().__init__(f"All fetchers failed for {url}: {len(attempts)} attempts")


class ScrapeResult(BaseModel):
    """Result of a scrape operation."""

    fetch: FetchResult
    data: BaseModel | dict | list[dict] | None = None
    from_cache: bool = False

    model_config = {"arbitrary_types_allowed": True}


class ScrapeClient:
    """Orchestrates fetching, caching, rate limiting, retries, and extraction."""

    def __init__(
        self,
        primary: PageFetcher,
        fallback: PageFetcher | None = None,
        rate_limiter: RateLimiter | None = None,
        cache: ResponseCache | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._rate_limiter = rate_limiter or RateLimiter()
        self._cache = cache
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    async def __aenter__(self) -> ScrapeClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close fetcher resources."""
        for fetcher in (self._primary, self._fallback):
            if fetcher is not None and hasattr(fetcher, "close"):
                await fetcher.close()

    async def scrape(
        self,
        url: str,
        *,
        render_js: bool = True,
        extraction: Any | None = None,
        schema: type[BaseModel] | None = None,
    ) -> ScrapeResult:
        """Fetch a URL, cache the result, and optionally extract structured data."""
        # 1. Cache check
        if self._cache is not None:
            cached = await self._cache.get(url, render_js)
            if cached is not None:
                data = None
                if extraction is not None or schema is not None:
                    data = await self._run_extraction(cached, extraction, schema)
                return ScrapeResult(fetch=cached, data=data, from_cache=True)

        # 2. Rate limit
        domain = urlparse(url).netloc
        await self._rate_limiter.wait(domain)

        # 3-5. Fetch with retries and fallback
        fetch_result = await self._fetch_with_fallback(url, render_js)

        # 6. Cache store
        if self._cache is not None:
            await self._cache.put(url, render_js, fetch_result)

        # 7. Extract
        data = None
        if extraction is not None or schema is not None:
            data = await self._run_extraction(fetch_result, extraction, schema)

        # 8. Return
        return ScrapeResult(fetch=fetch_result, data=data, from_cache=False)

    async def _fetch_with_fallback(
        self, url: str, render_js: bool
    ) -> FetchResult:
        """Try primary fetcher with retries, then fallback."""
        attempts: list[dict] = []

        for fetcher_name, fetcher in [("primary", self._primary), ("fallback", self._fallback)]:
            if fetcher is None:
                continue

            result = await self._fetch_with_retries(fetcher, fetcher_name, url, render_js, attempts)
            if result is not None:
                return result

        raise ScrapeError(url=url, attempts=attempts)

    async def _fetch_with_retries(
        self,
        fetcher: PageFetcher,
        fetcher_name: str,
        url: str,
        render_js: bool,
        attempts: list[dict],
    ) -> FetchResult | None:
        """Retry a single fetcher with exponential backoff + jitter.

        PermanentFetchError (4xx) is not retried — fails immediately.
        Transient errors (network, 5xx) are retried up to max_retries.
        """
        for attempt in range(self._max_retries):
            try:
                result = await fetcher.fetch(url, render_js=render_js)
                logger.info(
                    "fetch_success",
                    url=url,
                    fetcher=fetcher_name,
                    attempt=attempt + 1,
                )
                return result
            except PermanentFetchError as exc:
                # 4xx errors — do not retry
                attempts.append({
                    "fetcher": fetcher_name,
                    "attempt": attempt + 1,
                    "error": type(exc).__name__,
                    "message": str(exc),
                })
                logger.warning(
                    "fetch_permanent_error",
                    url=url,
                    fetcher=fetcher_name,
                    status_code=exc.status_code,
                )
                return None
            except Exception as exc:
                attempts.append({
                    "fetcher": fetcher_name,
                    "attempt": attempt + 1,
                    "error": type(exc).__name__,
                    "message": str(exc),
                })
                logger.warning(
                    "fetch_retry",
                    url=url,
                    fetcher=fetcher_name,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt < self._max_retries - 1:
                    delay = self._retry_base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)

        return None

    async def _run_extraction(
        self,
        fetch_result: FetchResult,
        extraction: Any | None,
        schema: type[BaseModel] | None,
    ) -> Any:
        """Run extraction on fetched content."""
        if extraction is None and schema is not None:
            extraction = LLMExtraction()

        content = fetch_result.markdown or fetch_result.html or ""
        return await extraction.extract(content, schema=schema)


def create_scrape_client(
    cache_dir: str | None = None,
    cache_ttl: int | None = None,
    rate_limit_default: float | None = None,
    max_retries: int | None = None,
    retry_base_delay: float | None = None,
) -> ScrapeClient:
    """Build a ScrapeClient with default config from env vars.

    If Cloudflare credentials are present, uses CloudflareFetcher as primary
    and Crawl4AiFetcher as fallback. Otherwise, uses Crawl4AiFetcher as primary
    with no fallback.
    """
    from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import (
        Crawl4AiFetcher,
    )

    _cache_dir = cache_dir if cache_dir is not None else os.environ.get("SCRAPE_CACHE_DIR", "data/cache")
    _cache_ttl = cache_ttl if cache_ttl is not None else int(os.environ.get("SCRAPE_CACHE_TTL", "21600"))
    _rate_default = rate_limit_default if rate_limit_default is not None else float(os.environ.get("SCRAPE_RATE_LIMIT_DEFAULT", "2.0"))
    _max_retries = max_retries if max_retries is not None else int(os.environ.get("SCRAPE_RETRY_MAX", "3"))
    _retry_delay = retry_base_delay if retry_base_delay is not None else float(os.environ.get("SCRAPE_RETRY_BASE_DELAY", "1.0"))

    cache = ResponseCache(cache_dir=_cache_dir, ttl=_cache_ttl)
    limiter = RateLimiter(default_delay=_rate_default)

    cf_account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN")

    if cf_account and cf_token:
        from tdc_auction_calendar.collectors.scraping.fetchers.cloudflare import (
            CloudflareFetcher,
        )

        primary = CloudflareFetcher(account_id=cf_account, api_token=cf_token)
        fallback = Crawl4AiFetcher()
    else:
        primary = Crawl4AiFetcher()
        fallback = None

    return ScrapeClient(
        primary=primary,
        fallback=fallback,
        rate_limiter=limiter,
        cache=cache,
        max_retries=_max_retries,
        retry_base_delay=_retry_delay,
    )
```

- [ ] **Step 4: Run all client tests to verify they pass**

Run: `uv run pytest tests/scraping/test_client.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/client.py tests/scraping/test_client.py
git commit -m "feat(scraping): add ScrapeClient with retry, fallback, and caching (issue #10)"
```

---

## Chunk 5: Public API + Final Integration

### Task 9: Wire up __init__.py exports and update collectors __init__.py

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/__init__.py`
- Modify: `src/tdc_auction_calendar/collectors/__init__.py`

- [ ] **Step 1: Update scraping __init__.py with public API exports**

```python
# src/tdc_auction_calendar/collectors/scraping/__init__.py
"""Shared scraping infrastructure.

Public API:
    ScrapeClient         — main client for fetching + extracting web data
    ScrapeResult         — result container
    ScrapeError          — raised when all fetchers fail
    PermanentFetchError  — raised for non-retryable errors (4xx)
    create_scrape_client — factory with env-var defaults
    FetchResult          — raw fetch result model
    LLMExtraction        — Claude-based extraction strategy
    CSSExtraction        — CSS selector-based extraction strategy
"""

from tdc_auction_calendar.collectors.scraping.client import (
    PermanentFetchError,
    ScrapeClient,
    ScrapeError,
    ScrapeResult,
    create_scrape_client,
)
from tdc_auction_calendar.collectors.scraping.extraction import (
    CSSExtraction,
    LLMExtraction,
)
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

__all__ = [
    "CSSExtraction",
    "FetchResult",
    "LLMExtraction",
    "PermanentFetchError",
    "ScrapeClient",
    "ScrapeError",
    "ScrapeResult",
    "create_scrape_client",
]
```

- [ ] **Step 2: Update collectors __init__.py**

```python
# src/tdc_auction_calendar/collectors/__init__.py
from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.statutory import StatutoryCollector

__all__ = ["BaseCollector", "StatutoryCollector"]
```

This stays the same — scraping is imported directly from `collectors.scraping` by collectors that need it, not re-exported at the top level.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass (existing + new scraping tests)

- [ ] **Step 4: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/__init__.py
git commit -m "feat(scraping): wire up public API exports (issue #10)"
```

---

### Task 10: Final verification and cleanup

- [ ] **Step 1: Run full test suite with coverage**

Run: `uv run pytest --cov=tdc_auction_calendar.collectors.scraping --cov-report=term-missing -v`
Expected: All tests pass, reasonable coverage across all scraping modules

- [ ] **Step 2: Verify imports work as expected**

Run: `uv run python -c "from tdc_auction_calendar.collectors.scraping import ScrapeClient, ScrapeResult, ScrapeError, PermanentFetchError, create_scrape_client, FetchResult, LLMExtraction, CSSExtraction; print('All imports OK')"`
Expected: "All imports OK"

- [ ] **Step 3: Verify existing tests still pass**

Run: `uv run pytest tests/test_base_collector.py tests/test_statutory_collector.py -v`
Expected: All existing tests still pass (no regressions)

- [ ] **Step 4: Final commit if any cleanup was needed**

```bash
git add -A
git commit -m "chore(scraping): final cleanup for scraping infrastructure (issue #10)"
```
