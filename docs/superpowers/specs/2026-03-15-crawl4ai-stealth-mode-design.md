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
- **`STEALTH`** (default): `BrowserConfig(headless=True, enable_stealth=True)` passed to `AsyncWebCrawler`. `CrawlerRunConfig(magic=True)` passed per-request in `arun()`.
- **`UNDETECTED`**: Same `BrowserConfig` as stealth, plus `UndetectedAdapter` wired through `AsyncPlaywrightCrawlerStrategy` and passed to `AsyncWebCrawler`. `CrawlerRunConfig(magic=True)` also used per-request.

### create_scrape_client() Changes

New `stealth: str | None = None` parameter. Defaults to `"stealth"` when not provided. Passes through to `Crawl4AiFetcher(stealth=StealthLevel(stealth))`. Both primary and fallback `Crawl4AiFetcher` instances receive the same level.

`ScrapeClient` itself is unchanged — it receives fetchers without caring about their config.

### Collector Usage

Existing collectors get stealth mode for free (default). Collectors targeting bot-protected sites opt into undetected mode:

```python
client = create_scrape_client(stealth="undetected")
```

### Testing

- **Unit tests (mocked):** Verify `_get_crawler()` creates correct config objects per `StealthLevel`. Mock `BrowserConfig`, `AsyncWebCrawler`, `UndetectedAdapter`, and `AsyncPlaywrightCrawlerStrategy` imports; assert called with expected args.
- **`create_scrape_client` tests:** Verify `stealth` param flows through to the fetcher.
- **No live integration tests** against blocked sites — environment-dependent and flaky. Manual verification post-implementation.
- **Existing tests** continue passing since injected-crawler tests bypass `_get_crawler()`.

### Files Changed

1. `src/tdc_auction_calendar/collectors/scraping/fetchers/crawl4ai.py` — `StealthLevel` enum, updated constructor and `_get_crawler()`
2. `src/tdc_auction_calendar/collectors/scraping/client.py` — `stealth` param on `create_scrape_client()`
3. `tests/scraping/test_crawl4ai.py` — new tests for stealth config wiring

### Sites This Unblocks

- `realauction.com` — custom bot detection
- `bid4assets.com` — Akamai Bot Manager
- `publicsurplus.com` — JS-only rendering
- `taxsales.lgbs.com` — JS-heavy map interface
- `lienhub.com` — JS-heavy app
