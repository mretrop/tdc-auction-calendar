# Crawl4AI Stealth Mode Design

**Issue:** [#49 — Enable Crawl4AI stealth mode for bot-protected sites](https://github.com/mretrop/tdc-auction-calendar/issues/49)
**Date:** 2026-03-15

## Problem

Several high-value auction vendor sites (RealAuction, Bid4Assets, etc.) block datacenter IPs. Crawl4AI runs locally from residential IPs and supports stealth features, but our current implementation doesn't enable them.

## Design

### StealthLevel Enum

New `StrEnum` co-located in `collectors/scraping/fetchers/crawl4ai.py`:

```python
class StealthLevel(StrEnum):
    OFF = "off"
    STEALTH = "stealth"          # BrowserConfig(enable_stealth=True)
    UNDETECTED = "undetected"    # enable_stealth + UndetectedAdapter
```

### Crawl4AiFetcher Changes

Constructor gains `stealth: StealthLevel = StealthLevel.STEALTH`.

The lazy `_get_crawler()` method configures crawl4ai based on the level:

- **`OFF`**: Plain `AsyncWebCrawler()` — current behavior.
- **`STEALTH`** (default):
  ```python
  browser_config = BrowserConfig(headless=True, enable_stealth=True)
  crawler = AsyncWebCrawler(config=browser_config)
  ```
- **`UNDETECTED`**: Strategy-based construction — `config=` is NOT passed alongside `crawler_strategy=`:
  ```python
  browser_config = BrowserConfig(headless=True, enable_stealth=True)
  strategy = AsyncPlaywrightCrawlerStrategy(
      browser_config=browser_config,
      browser_adapter=UndetectedAdapter(),
  )
  crawler = AsyncWebCrawler(crawler_strategy=strategy)
  ```

Logs the stealth level on init: `logger.info("crawl4ai_init", stealth=self._stealth.value)`.

Note: The crawler is created lazily and cached. Changing `stealth` after construction has no effect once `_get_crawler()` has been called.

#### fetch() refactor: CrawlerRunConfig

The current `fetch()` passes `js_code` and `wait_for` as loose kwargs to `arun()`. For `STEALTH` and `UNDETECTED` levels, we need `CrawlerRunConfig(magic=True)` per-request. Since `CrawlerRunConfig` accepts `js_code` and `wait_for` as constructor params, `fetch()` will be refactored to always build a `CrawlerRunConfig`:

```python
from crawl4ai.async_configs import CrawlerRunConfig

run_config = CrawlerRunConfig(
    js_code=js_code,        # None if not provided
    wait_for=wait_for,      # None if not provided
    magic=(self._stealth != StealthLevel.OFF),
)
result = await crawler.arun(url, config=run_config)
```

This replaces the current loose-kwargs approach for all stealth levels, keeping `fetch()` consistent.

### create_scrape_client() Changes

New `stealth: StealthLevel = StealthLevel.STEALTH` parameter (typed as the enum, not a raw string). Passes through to `Crawl4AiFetcher(stealth=stealth)`. Both primary and fallback `Crawl4AiFetcher` instances receive the same level. When Cloudflare is primary, the stealth param only affects the fallback `Crawl4AiFetcher`.

`ScrapeClient` itself is unchanged — it receives fetchers without caring about their config.

### Collector Usage

Existing collectors get stealth mode for free (default). Collectors targeting bot-protected sites opt into undetected mode:

```python
from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import StealthLevel

client = create_scrape_client(stealth=StealthLevel.UNDETECTED)
```

### Testing

- **Unit tests (mocked):** Verify `_get_crawler()` creates correct config objects per `StealthLevel`. Mock `BrowserConfig`, `AsyncWebCrawler`, `UndetectedAdapter`, and `AsyncPlaywrightCrawlerStrategy` imports; assert called with expected args.
- **`create_scrape_client` tests:** Verify `stealth` param flows through to the fetcher.
- **No live integration tests** against blocked sites — environment-dependent and flaky. Manual verification post-implementation.
- **Existing tests** continue passing since injected-crawler tests bypass `_get_crawler()`.

### Files Changed

1. `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py` — `StealthLevel` enum, updated constructor, `_get_crawler()`, and `fetch()` refactor
2. `src/tdc_auction_calendar/collectors/scraping/client.py` — `stealth` param on `create_scrape_client()`
3. `src/tdc_auction_calendar/collectors/scraping/__init__.py` — re-export `StealthLevel`
4. `tests/scraping/test_crawl4ai.py` — new tests for stealth config wiring

### Manual Verification

After implementation, verify stealth mode works against a previously-blocked site:

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

Expected: 200 status with non-trivial HTML content.

### Sites This Unblocks

- `realauction.com` — custom bot detection
- `bid4assets.com` — Akamai Bot Manager
- `publicsurplus.com` — JS-only rendering
- `taxsales.lgbs.com` — JS-heavy map interface
- `lienhub.com` — JS-heavy app
