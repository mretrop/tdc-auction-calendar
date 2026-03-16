# Crawl4AI Stealth Mode Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Crawl4AI stealth and undetected browser modes so the fetcher can bypass bot protection on vendor auction sites.

**Architecture:** Add a `StealthLevel` enum (`off`/`stealth`/`undetected`) to `Crawl4AiFetcher`. Stealth is the default for all crawl4ai usage. Undetected mode is opt-in per collector via `create_scrape_client(stealth=StealthLevel.UNDETECTED)`. The `fetch()` method is refactored to use `CrawlerRunConfig` instead of loose kwargs.

**Tech Stack:** crawl4ai (`BrowserConfig`, `CrawlerRunConfig`, `AsyncPlaywrightCrawlerStrategy`, `UndetectedAdapter`), pytest, unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-15-crawl4ai-stealth-mode-design.md`

---

## Chunk 1: StealthLevel enum and fetcher constructor

### Task 1: Add StealthLevel enum and update constructor

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py:1-20`
- Test: `tests/scraping/test_crawl4ai.py`

- [ ] **Step 1: Write test for StealthLevel enum values**

```python
# tests/scraping/test_crawl4ai.py — add at top of file after existing imports

from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import StealthLevel


def test_stealth_level_values():
    """StealthLevel enum has expected string values."""
    assert StealthLevel.OFF == "off"
    assert StealthLevel.STEALTH == "stealth"
    assert StealthLevel.UNDETECTED == "undetected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scraping/test_crawl4ai.py::test_stealth_level_values -v`
Expected: FAIL — `ImportError: cannot import name 'StealthLevel'`

- [ ] **Step 3: Add StealthLevel enum to crawl4ai.py**

Add after the existing imports in `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py`:

```python
from enum import StrEnum


class StealthLevel(StrEnum):
    """Controls anti-bot evasion level for the Crawl4AI browser."""

    OFF = "off"
    STEALTH = "stealth"
    UNDETECTED = "undetected"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scraping/test_crawl4ai.py::test_stealth_level_values -v`
Expected: PASS

- [ ] **Step 5: Write test for constructor default stealth level**

```python
# tests/scraping/test_crawl4ai.py

async def test_default_stealth_is_stealth():
    """Crawl4AiFetcher defaults to STEALTH level."""
    fetcher = Crawl4AiFetcher()
    assert fetcher._stealth == StealthLevel.STEALTH


async def test_constructor_accepts_stealth_level():
    """Crawl4AiFetcher accepts explicit stealth level."""
    fetcher = Crawl4AiFetcher(stealth=StealthLevel.OFF)
    assert fetcher._stealth == StealthLevel.OFF

    fetcher2 = Crawl4AiFetcher(stealth=StealthLevel.UNDETECTED)
    assert fetcher2._stealth == StealthLevel.UNDETECTED
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_crawl4ai.py::test_default_stealth_is_stealth tests/scraping/test_crawl4ai.py::test_constructor_accepts_stealth_level -v`
Expected: FAIL — `AttributeError: 'Crawl4AiFetcher' object has no attribute '_stealth'`

- [ ] **Step 7: Update Crawl4AiFetcher constructor**

In `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py`, update the `__init__`:

```python
def __init__(
    self,
    crawler: Any = None,
    stealth: StealthLevel = StealthLevel.STEALTH,
) -> None:
    self._crawler = crawler
    self._owns_crawler = crawler is None
    self._stealth = stealth
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_crawl4ai.py -v`
Expected: ALL PASS (new tests + existing tests)

- [ ] **Step 9: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py tests/scraping/test_crawl4ai.py
git commit -m "feat: add StealthLevel enum and constructor param to Crawl4AiFetcher (#49)"
```

---

## Chunk 2: _get_crawler() stealth configuration

### Task 2: Configure _get_crawler() for STEALTH level

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py:22-40`
- Test: `tests/scraping/test_crawl4ai.py`

- [ ] **Step 1: Write test for STEALTH level crawler init**

This test mocks the crawl4ai imports to verify `BrowserConfig` and `AsyncWebCrawler` are called with the right args.

```python
# tests/scraping/test_crawl4ai.py

async def test_get_crawler_stealth_configures_browser():
    """STEALTH level passes BrowserConfig(headless=True, enable_stealth=True) to AsyncWebCrawler."""
    mock_browser_config = MagicMock()
    mock_browser_config_cls = MagicMock(return_value=mock_browser_config)

    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.arun = AsyncMock(return_value=_mock_crawl_result())
    mock_web_crawler_cls = MagicMock(return_value=mock_crawler_instance)

    mock_configs = MagicMock()
    mock_configs.BrowserConfig = mock_browser_config_cls
    mock_configs.CrawlerRunConfig = MagicMock()

    mock_crawl4ai = MagicMock()
    mock_crawl4ai.AsyncWebCrawler = mock_web_crawler_cls

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.STEALTH)

    with patch.dict("sys.modules", {
        "crawl4ai": mock_crawl4ai,
        "crawl4ai.async_configs": mock_configs,
    }):
        await fetcher.fetch("https://example.com")

    mock_browser_config_cls.assert_called_once_with(headless=True, enable_stealth=True)
    mock_web_crawler_cls.assert_called_once_with(config=mock_browser_config)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scraping/test_crawl4ai.py::test_get_crawler_stealth_configures_browser -v`
Expected: FAIL — current `_get_crawler()` doesn't use `BrowserConfig`

- [ ] **Step 3: Write test for OFF level crawler init**

```python
# tests/scraping/test_crawl4ai.py

async def test_get_crawler_off_uses_plain_crawler():
    """OFF level creates AsyncWebCrawler with no config."""
    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.arun = AsyncMock(return_value=_mock_crawl_result())
    mock_web_crawler_cls = MagicMock(return_value=mock_crawler_instance)

    mock_configs = MagicMock()
    mock_configs.CrawlerRunConfig = MagicMock()

    mock_crawl4ai = MagicMock()
    mock_crawl4ai.AsyncWebCrawler = mock_web_crawler_cls

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.OFF)

    with patch.dict("sys.modules", {
        "crawl4ai": mock_crawl4ai,
        "crawl4ai.async_configs": mock_configs,
    }):
        await fetcher.fetch("https://example.com")

    mock_web_crawler_cls.assert_called_once_with()
```

- [ ] **Step 4: Update _get_crawler() for OFF and STEALTH levels**

Replace the `_get_crawler()` method in `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py`:

```python
async def _get_crawler(self) -> Any:
    if self._crawler is None:
        try:
            from crawl4ai import AsyncWebCrawler
            from crawl4ai.async_configs import BrowserConfig
        except ImportError as exc:
            raise RuntimeError(
                "crawl4ai is required but not installed. Install with: uv add crawl4ai"
            ) from exc

        logger.info("crawl4ai_init", stealth=self._stealth.value)

        if self._stealth == StealthLevel.OFF:
            crawler = AsyncWebCrawler()
        elif self._stealth == StealthLevel.STEALTH:
            browser_config = BrowserConfig(headless=True, enable_stealth=True)
            crawler = AsyncWebCrawler(config=browser_config)
        else:
            # UNDETECTED — handled in next task
            raise NotImplementedError(f"StealthLevel.UNDETECTED not yet implemented")

        try:
            await crawler.__aenter__()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialize headless browser: {exc}. "
                "Try running: crawl4ai-setup"
            ) from exc
        self._crawler = crawler
    return self._crawler
```

- [ ] **Step 5: Run all tests to verify they pass**

Run: `uv run pytest tests/scraping/test_crawl4ai.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py tests/scraping/test_crawl4ai.py
git commit -m "feat: configure _get_crawler() for STEALTH and OFF levels (#49)"
```

### Task 3: Configure _get_crawler() for UNDETECTED level

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py`
- Test: `tests/scraping/test_crawl4ai.py`

- [ ] **Step 1: Write test for UNDETECTED level crawler init**

```python
# tests/scraping/test_crawl4ai.py

async def test_get_crawler_undetected_uses_adapter_and_strategy():
    """UNDETECTED level uses UndetectedAdapter + AsyncPlaywrightCrawlerStrategy."""
    mock_browser_config = MagicMock()
    mock_browser_config_cls = MagicMock(return_value=mock_browser_config)

    mock_adapter = MagicMock()
    mock_adapter_cls = MagicMock(return_value=mock_adapter)

    mock_strategy = MagicMock()
    mock_strategy_cls = MagicMock(return_value=mock_strategy)

    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.arun = AsyncMock(return_value=_mock_crawl_result())
    mock_web_crawler_cls = MagicMock(return_value=mock_crawler_instance)

    mock_configs = MagicMock()
    mock_configs.BrowserConfig = mock_browser_config_cls
    mock_configs.CrawlerRunConfig = MagicMock()

    mock_crawl4ai = MagicMock()
    mock_crawl4ai.AsyncWebCrawler = mock_web_crawler_cls
    mock_crawl4ai.UndetectedAdapter = mock_adapter_cls

    mock_strategy_module = MagicMock()
    mock_strategy_module.AsyncPlaywrightCrawlerStrategy = mock_strategy_cls

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.UNDETECTED)

    with patch.dict("sys.modules", {
        "crawl4ai": mock_crawl4ai,
        "crawl4ai.async_configs": mock_configs,
        "crawl4ai.async_crawler_strategy": mock_strategy_module,
    }):
        await fetcher.fetch("https://example.com")

    mock_browser_config_cls.assert_called_once_with(headless=True, enable_stealth=True)
    mock_adapter_cls.assert_called_once_with()
    mock_strategy_cls.assert_called_once_with(
        browser_config=mock_browser_config,
        browser_adapter=mock_adapter,
    )
    mock_web_crawler_cls.assert_called_once_with(crawler_strategy=mock_strategy)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scraping/test_crawl4ai.py::test_get_crawler_undetected_uses_adapter_and_strategy -v`
Expected: FAIL — `NotImplementedError: StealthLevel.UNDETECTED not yet implemented`

- [ ] **Step 3: Implement UNDETECTED branch in _get_crawler()**

Replace the `NotImplementedError` else branch:

```python
else:
    # UNDETECTED — uses UndetectedAdapter for tougher bot protection
    from crawl4ai import UndetectedAdapter
    from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

    browser_config = BrowserConfig(headless=True, enable_stealth=True)
    adapter = UndetectedAdapter()
    strategy = AsyncPlaywrightCrawlerStrategy(
        browser_config=browser_config,
        browser_adapter=adapter,
    )
    crawler = AsyncWebCrawler(crawler_strategy=strategy)
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `uv run pytest tests/scraping/test_crawl4ai.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py tests/scraping/test_crawl4ai.py
git commit -m "feat: add UNDETECTED level with UndetectedAdapter (#49)"
```

---

## Chunk 3: fetch() refactor to CrawlerRunConfig

### Task 4: Refactor fetch() to use CrawlerRunConfig

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py:42-87`
- Test: `tests/scraping/test_crawl4ai.py`

- [ ] **Step 1: Write test for magic=True in arun() when stealth is on**

```python
# tests/scraping/test_crawl4ai.py

async def test_fetch_uses_crawler_run_config_with_magic():
    """STEALTH level passes CrawlerRunConfig(magic=True) to arun()."""
    mock_run_config = MagicMock()
    mock_run_config_cls = MagicMock(return_value=mock_run_config)

    mock_browser_config = MagicMock()
    mock_browser_config_cls = MagicMock(return_value=mock_browser_config)

    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.arun = AsyncMock(return_value=_mock_crawl_result())
    mock_web_crawler_cls = MagicMock(return_value=mock_crawler_instance)

    mock_configs = MagicMock()
    mock_configs.BrowserConfig = mock_browser_config_cls
    mock_configs.CrawlerRunConfig = mock_run_config_cls

    mock_crawl4ai = MagicMock()
    mock_crawl4ai.AsyncWebCrawler = mock_web_crawler_cls

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.STEALTH)

    with patch.dict("sys.modules", {
        "crawl4ai": mock_crawl4ai,
        "crawl4ai.async_configs": mock_configs,
    }):
        await fetcher.fetch("https://example.com", js_code="click()", wait_for="#results")

    mock_run_config_cls.assert_called_once_with(
        js_code="click()",
        wait_for="#results",
        magic=True,
    )
    mock_crawler_instance.arun.assert_called_once_with("https://example.com", config=mock_run_config)
```

- [ ] **Step 2: Write test for magic=False when stealth is OFF**

```python
# tests/scraping/test_crawl4ai.py

async def test_fetch_uses_crawler_run_config_without_magic_when_off():
    """OFF level passes CrawlerRunConfig(magic=False) to arun()."""
    mock_run_config = MagicMock()
    mock_run_config_cls = MagicMock(return_value=mock_run_config)

    mock_configs = MagicMock()
    mock_configs.CrawlerRunConfig = mock_run_config_cls

    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.arun = AsyncMock(return_value=_mock_crawl_result())
    mock_web_crawler_cls = MagicMock(return_value=mock_crawler_instance)

    mock_crawl4ai = MagicMock()
    mock_crawl4ai.AsyncWebCrawler = mock_web_crawler_cls

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.OFF)

    with patch.dict("sys.modules", {
        "crawl4ai": mock_crawl4ai,
        "crawl4ai.async_configs": mock_configs,
    }):
        await fetcher.fetch("https://example.com")

    mock_run_config_cls.assert_called_once_with(
        js_code=None,
        wait_for=None,
        magic=False,
    )
```

- [ ] **Step 3: Refactor fetch() to use CrawlerRunConfig**

Replace the `fetch()` method body (after the logger.info call) in `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py`:

```python
async def fetch(
    self,
    url: str,
    *,
    render_js: bool = True,
    json_options: dict | None = None,
    js_code: str | None = None,
    wait_for: str | None = None,
) -> FetchResult:
    """Fetch a page using the local headless browser."""
    logger.info("crawl4ai_fetch_start", url=url, render_js=render_js)

    crawler = await self._get_crawler()
    try:
        from crawl4ai.async_configs import CrawlerRunConfig

        run_config = CrawlerRunConfig(
            js_code=js_code,
            wait_for=wait_for,
            magic=(self._stealth != StealthLevel.OFF),
        )
        result = await crawler.arun(url, config=run_config)
    except (OSError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Crawl4AI failed for {url}: {exc}") from exc

    if hasattr(result, "status_code") and result.status_code is not None:
        status_code = result.status_code
    else:
        logger.warning(
            "crawl4ai_missing_status_code",
            url=url,
            result_type=type(result).__name__,
        )
        status_code = 200
    if 400 <= status_code < 500:
        raise PermanentFetchError(status_code, f"Crawl4AI got {status_code} for {url}")
    if status_code >= 500:
        raise RuntimeError(f"Crawl4AI got server error {status_code} for {url}")

    return FetchResult(
        url=url,
        html=result.html,
        markdown=result.markdown,
        status_code=status_code,
        fetcher="crawl4ai",
    )
```

- [ ] **Step 4: Update existing injected-crawler tests for CrawlerRunConfig**

After refactoring `fetch()`, the `CrawlerRunConfig` import happens at call time. Tests that inject a mock crawler need `crawl4ai.async_configs` in `sys.modules`. Also, two existing tests assert `arun()` kwargs directly — these must be rewritten since `arun()` now receives `config=<CrawlerRunConfig>` instead of loose kwargs.

Add a helper fixture (NOT autouse — only used by injected-crawler tests):

```python
@pytest.fixture
def mock_run_config():
    """Provide mock CrawlerRunConfig for injected-crawler tests."""
    mock_config_cls = MagicMock(return_value=MagicMock())
    mock_configs = MagicMock()
    mock_configs.CrawlerRunConfig = mock_config_cls
    with patch.dict("sys.modules", {"crawl4ai.async_configs": mock_configs}):
        yield mock_config_cls
```

Update `mock_crawler` fixture to depend on it:

```python
@pytest.fixture
def mock_crawler(mock_run_config):
    """Provide a mock AsyncWebCrawler with a default successful result."""
    crawler = AsyncMock()
    crawler.arun.return_value = _mock_crawl_result()
    return crawler
```

Rewrite `test_fetch_passes_js_code_and_wait_for` (currently line 88):

```python
async def test_fetch_passes_js_code_and_wait_for(mock_crawler, mock_run_config):
    """Crawl4AI fetcher passes js_code and wait_for via CrawlerRunConfig."""
    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    js = "document.querySelector('#search').click();"
    wait = "#results"

    await fetcher.fetch("https://example.com", js_code=js, wait_for=wait)

    mock_run_config.assert_called_once_with(
        js_code=js,
        wait_for=wait,
        magic=True,  # default stealth=STEALTH → magic=True
    )
```

Rewrite `test_fetch_omits_js_code_when_none` (currently line 103):

```python
async def test_fetch_omits_js_code_when_none(mock_crawler, mock_run_config):
    """When js_code/wait_for are None, CrawlerRunConfig gets None values."""
    fetcher = Crawl4AiFetcher(crawler=mock_crawler)

    await fetcher.fetch("https://example.com")

    mock_run_config.assert_called_once_with(
        js_code=None,
        wait_for=None,
        magic=True,
    )
```

Also update all other tests that use the `mock_crawler` fixture or `Crawl4AiFetcher(crawler=mock_crawler)` to accept `mock_run_config` — these are: `test_fetch_success`, `test_fetch_passes_url_to_crawler`, `test_fetch_error_propagates`, `test_fetch_4xx_raises_permanent_error`, `test_fetch_5xx_raises_runtime_error`, `test_fetch_wraps_generic_exception`, `test_fetch_missing_status_code_defaults_to_200`, `test_fetch_none_status_code_defaults_to_200`. Each of these needs `mock_run_config` as a fixture param so the `crawl4ai.async_configs` module is available during `fetch()`.

- [ ] **Step 5: Run all tests to verify they pass**

Run: `uv run pytest tests/scraping/test_crawl4ai.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py tests/scraping/test_crawl4ai.py
git commit -m "refactor: use CrawlerRunConfig in fetch() with magic mode (#49)"
```

---

## Chunk 4: create_scrape_client() integration and re-export

### Task 5: Add stealth param to create_scrape_client()

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/client.py:291-339`
- Modify: `src/tdc_auction_calendar/collectors/scraping/__init__.py`
- Test: `tests/scraping/test_client.py`

- [ ] **Step 1: Write test for default stealth in create_scrape_client**

```python
# tests/scraping/test_client.py — add near existing create_scrape_client tests

from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import StealthLevel


def test_create_scrape_client_default_stealth(tmp_path, monkeypatch):
    """Default create_scrape_client uses STEALTH level on Crawl4AiFetcher."""
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    client = create_scrape_client(cache_dir=str(tmp_path))
    assert isinstance(client._primary, Crawl4AiFetcher)
    assert client._primary._stealth == StealthLevel.STEALTH


def test_create_scrape_client_undetected_stealth(tmp_path, monkeypatch):
    """Explicit UNDETECTED stealth flows to Crawl4AiFetcher."""
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    client = create_scrape_client(cache_dir=str(tmp_path), stealth=StealthLevel.UNDETECTED)
    assert client._primary._stealth == StealthLevel.UNDETECTED


def test_create_scrape_client_stealth_on_fallback(tmp_path, monkeypatch):
    """With Cloudflare primary, stealth param applies to fallback Crawl4AiFetcher."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")

    client = create_scrape_client(
        cache_dir=str(tmp_path),
        stealth=StealthLevel.UNDETECTED,
    )
    assert isinstance(client._fallback, Crawl4AiFetcher)
    assert client._fallback._stealth == StealthLevel.UNDETECTED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_client.py::test_create_scrape_client_default_stealth -v`
Expected: FAIL — `TypeError: create_scrape_client() got an unexpected keyword argument 'stealth'` or missing `_stealth` attribute

- [ ] **Step 3: Update create_scrape_client() signature and body**

In `src/tdc_auction_calendar/collectors/scraping/client.py`, update `create_scrape_client`:

```python
def create_scrape_client(
    cache_dir: str | None = None,
    cache_ttl: int | None = None,
    rate_limit_default: float | None = None,
    max_retries: int | None = None,
    retry_base_delay: float | None = None,
    stealth: StealthLevel | None = None,
) -> ScrapeClient:
```

Add the import at the top of the function body (lazy, like the existing pattern):

```python
from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import (
    Crawl4AiFetcher,
    StealthLevel,
)

_stealth = stealth if stealth is not None else StealthLevel.STEALTH
```

Update the two `Crawl4AiFetcher()` calls:

```python
fallback = Crawl4AiFetcher(stealth=_stealth)
# and
primary = Crawl4AiFetcher(stealth=_stealth)
```

- [ ] **Step 4: Run all client tests**

Run: `uv run pytest tests/scraping/test_client.py -v`
Expected: ALL PASS

- [ ] **Step 5: Re-export StealthLevel from scraping __init__.py**

In `src/tdc_auction_calendar/collectors/scraping/__init__.py`, add:

```python
from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import StealthLevel
```

And add `"StealthLevel"` to the `__all__` list.

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/client.py src/tdc_auction_calendar/collectors/scraping/__init__.py tests/scraping/test_client.py
git commit -m "feat: add stealth param to create_scrape_client and re-export StealthLevel (#49)"
```

---

## Chunk 5: Manual verification

### Task 6: Verify against a previously-blocked site

- [ ] **Step 1: Run manual verification script**

```bash
uv run python -c "
import asyncio
from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import Crawl4AiFetcher, StealthLevel

async def test():
    fetcher = Crawl4AiFetcher(stealth=StealthLevel.UNDETECTED)
    result = await fetcher.fetch('https://www.realauction.com')
    print(f'Status: {result.status_code}')
    print(f'HTML length: {len(result.html or \"\")}')
    await fetcher.close()

asyncio.run(test())
"
```

Expected: 200 status with non-trivial HTML content (>1000 chars).

- [ ] **Step 2: If verification succeeds, final commit and close issue**

```bash
gh issue close 49 --comment "Stealth mode implemented and verified against realauction.com"
```
